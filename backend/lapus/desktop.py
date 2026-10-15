"""Entry point for the packaged desktop app (see packaging/lapus.spec).

Runs the same FastAPI app as `uvicorn lapus.api.app:app`, but as a
double-click executable rather than a command someone types: starts the
server, opens the default browser at it, and keeps a console window open for
as long as the app runs. Closing that window, or Ctrl+C in it, stops Lapus.

The console is deliberate. It is where the app says which specification
database it found and whether the parser-owned data is protected -- the two
things worth knowing before trusting what the screen shows -- and it is the
app's off switch.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from .api.app import app
from .db.engine import staging_file_exists
from .settings import load_settings


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _open_browser_when_ready(url: str, host: str, port: int) -> None:
    for _ in range(50):  # ~10s before giving up
        if _port_is_open(host, port):
            webbrowser.open(url)
            return
        time.sleep(0.2)
    print(f"The server did not start in time -- open {url} manually.")


def main() -> None:
    settings = load_settings()
    host, port = settings.host, settings.port
    url = f"http://{host}:{port}/"

    if _port_is_open(host, port):
        # Already running -- the executable was double-clicked a second time.
        # Focus the existing instance rather than failing to bind a port.
        print(f"Lapus is already running. Opening {url}")
        webbrowser.open(url)
        return

    print("Starting Lapus...")
    print(f"Opening {url} in your browser.")
    print("Keep this window open while you are using Lapus; closing it stops the app.\n")

    staging = settings.staging_path
    if staging is not None:
        if staging_file_exists(str(staging)):
            print(f"Specification database: {staging}")
        else:
            # Said plainly here as well as in the UI: a console that scrolls
            # past an error is how a user ends up staring at an empty screen.
            print(f"Specification database NOT FOUND at: {staging}")
            print("  Set LAPUS_DATABASE_URL to the Spec_Stage.db your parser produced,")
            print("  or put Spec_Stage.db in the folder you run Lapus from.")
        print(f"Your change requests: {settings.lapus_database_url}")
    else:
        # A server backend keeps change requests in its own `lapus` schema;
        # naming the SQLite path here would point the user at a file that is
        # never written. The DSN is not printed either -- it carries a password.
        print("Specification database: configured server database")
        print("Your change requests: the lapus schema in that same database")
    print("Parser-owned specification data is opened read-only; Lapus cannot modify it.")
    print(f"Signed in as: {settings.dev_user_email}\n")

    # Frozen console apps buffer stdout well past the point of usefulness once
    # uvicorn.run() blocks for the rest of the process's life.
    sys.stdout.flush()

    threading.Thread(
        target=_open_browser_when_ready, args=(url, host, port), daemon=True
    ).start()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
