"""SQLite backend: parser data read-only, Lapus data in an attached schema.

The central trick, and the reason the read/write boundary in AGENTS.md is a
guarantee rather than a convention:

    main   = Spec_Stage.db  opened with mode=ro   -> T00-T11, physically read-only
    lapus  = lapus.db       attached with mode=rwc -> change requests, writable

SQLite applies open flags per attached database, so a stray UPDATE against
`t03_bill_of_materials` fails inside the engine with "attempt to write a
readonly database". No amount of application bugs, and no SQL injected through
a field name, can mutate parser-owned data through this connection.

Two further benefits fall out of it:

* Schema-qualified SQL (`lapus.change_request`) is written once and runs
  unchanged on PostgreSQL and SQL Server, where `lapus` is a real schema.
* App data lives in its own file, so re-running the parser -- which drops and
  recreates staging rows -- cannot touch a single change request, and the
  staging database can be replaced wholesale by copying one file.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

from .dialect import SQLITE
from .engine import Database, DatabaseError

LAPUS_SCHEMA = "lapus"


def _file_uri(path: Path, mode: str) -> str:
    """A SQLite URI for a path, safe for spaces and Windows drive letters."""
    resolved = path.expanduser().resolve()
    as_posix = resolved.as_posix()
    # Windows paths ("C:/Users/...") need a leading slash to be a valid URI.
    if not as_posix.startswith("/"):
        as_posix = "/" + as_posix
    return f"file:{quote(as_posix)}?mode={mode}"


def connect_sqlite(staging_url: str, lapus_url: str) -> Database:
    staging_path = Path(staging_url.removeprefix("sqlite://")).expanduser()
    lapus_path = Path(lapus_url.removeprefix("sqlite://")).expanduser()

    if not staging_path.is_file():
        raise DatabaseError(
            f"No specification database found at {staging_path}. "
            "Point LAPUS_DATABASE_URL at the Spec_Stage.db the parser produced."
        )

    lapus_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        connection = sqlite3.connect(
            _file_uri(staging_path, "ro"),
            uri=True,
            # The API is served from a thread pool; the Database wrapper
            # serialises access with its own lock.
            check_same_thread=False,
        )
        connection.execute(
            f"ATTACH DATABASE ? AS {LAPUS_SCHEMA}", (_file_uri(lapus_path, "rwc"),)
        )
    except sqlite3.Error as exc:
        raise DatabaseError(f"Could not open the specification database: {exc}") from exc

    # WAL keeps the Lapus store readable while a change request is being
    # written, and foreign keys are off by default in SQLite -- both matter
    # for the workflow tables, neither can affect the read-only staging file.
    connection.execute(f"PRAGMA {LAPUS_SCHEMA}.journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")

    return Database(connection, SQLITE)


def staging_is_readonly(database: Database) -> bool:
    """Confirm the staging boundary is actually in force.

    Called at startup so a misconfiguration surfaces immediately, and used by
    the test suite as the direct proof that T01-T11 cannot be written.
    """
    try:
        database.execute("UPDATE t00_documents SET filename = filename WHERE 1 = 0")
    except DatabaseError:
        return True
    return False
