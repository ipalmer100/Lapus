"""PyInstaller's entry script.

Kept separate from lapus/desktop.py so the frozen build has a plain top-level
script to point at, rather than relying on `python -m` module invocation
inside a frozen executable.
"""

import multiprocessing

from lapus.desktop import main

if __name__ == "__main__":
    # Harmless where it is not needed, and required on Windows if any code
    # path ever reaches multiprocessing: without it a worker process
    # re-launches the whole app instead of becoming a worker.
    multiprocessing.freeze_support()
    main()
