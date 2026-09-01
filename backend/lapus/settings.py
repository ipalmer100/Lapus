"""Runtime configuration, resolved once at startup.

Everything here can be set through the environment (see `.env.example`), but
every value has a working default so double-clicking the packaged executable
launches a usable app with no configuration at all -- which is the whole point
of shipping this as a desktop exe rather than a service someone has to deploy.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

# The staging database the V5.2 parser produces. The parser's own default
# output location is `Desktop\Specs\Spec_Stage.db`, so that is where we look
# first; a packaged app run by a business user will normally find it there
# without anyone setting a variable.
DEFAULT_DB_FILENAME = "Spec_Stage.db"


def _default_staging_db() -> Path:
    """Best guess at the parser's SQLite output, in priority order."""
    home = Path.home()
    candidates = [
        Path.cwd() / DEFAULT_DB_FILENAME,
        home / "Desktop" / "Specs" / DEFAULT_DB_FILENAME,
        home / "Desktop" / DEFAULT_DB_FILENAME,
        home / DEFAULT_DB_FILENAME,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # Nothing found: return the conventional parser location anyway so the
    # error message names the path the user most likely meant, rather than
    # something arbitrary like the current working directory.
    return home / "Desktop" / "Specs" / DEFAULT_DB_FILENAME


def _app_data_dir() -> Path:
    """Where Lapus keeps its own writable data.

    Deliberately *not* next to the executable: a packaged app can live in
    Program Files or on a read-only share, and change requests must survive
    rebuilding or replacing the app folder.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "Lapus"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Resolved application settings."""

    # Connection string for the parser-owned staging data. A bare filesystem
    # path is understood as SQLite; `postgresql://` and `mssql://` URLs select
    # the other dialects once those backends are wired up.
    database_url: str

    # Where Lapus writes. For SQLite this is a separate database file attached
    # as the `lapus` schema, so app data and parser data are never in the same
    # file. For a server database it is a real schema inside the same database.
    lapus_database_url: str

    # Identity used for created_by / submitted_by / decided_by until real
    # authentication is wired in (explicitly a POC affordance -- see AGENTS.md).
    dev_user_email: str

    # Whether the current user may approve/reject change requests and see the
    # parser-health admin area.
    dev_user_is_approver: bool

    # Whether one person may approve a request they submitted themselves.
    # Production practice is separation of duties, and the workflow enforces it
    # when this is off. It defaults ON because the POC runs as a single
    # configured identity: with it off, nothing could ever be approved and the
    # approval queue could not be demonstrated at all. Turn it off as soon as
    # real authentication gives Lapus more than one user.
    allow_self_approval: bool

    host: str
    port: int
    frontend_origin: str

    @property
    def staging_path(self) -> Path | None:
        """Filesystem path of the SQLite staging database, if that is the dialect."""
        if "://" in self.database_url:
            return None
        return Path(self.database_url).expanduser()


def load_settings() -> Settings:
    database_url = os.environ.get("LAPUS_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        database_url = str(_default_staging_db())

    lapus_database_url = os.environ.get("LAPUS_APP_DATABASE_URL")
    if not lapus_database_url:
        # Default the app-owned store next to the user's other app data rather
        # than beside the staging file, which may sit on a read-only share.
        lapus_database_url = str(_app_data_dir() / "lapus.db")

    return Settings(
        database_url=database_url,
        lapus_database_url=lapus_database_url,
        dev_user_email=os.environ.get("DEV_USER_EMAIL", "developer@example.com"),
        dev_user_is_approver=_env_flag("LAPUS_DEV_USER_IS_APPROVER", default=True),
        allow_self_approval=_env_flag("LAPUS_ALLOW_SELF_APPROVAL", default=True),
        host=os.environ.get("BACKEND_HOST", "127.0.0.1"),
        port=int(os.environ.get("BACKEND_PORT", "8770")),
        frontend_origin=os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173"),
    )
