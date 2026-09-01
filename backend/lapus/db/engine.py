"""Connection handling and the query interface repositories are written against.

Repositories never see a DB-API connection. They see `Database`, which takes
SQL with `?` placeholders and returns plain dicts. That is what makes the
SQLite -> SQL Server migration a backend swap rather than a rewrite.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .dialect import Dialect, dialect_for_url

Row = dict[str, Any]


class DatabaseError(RuntimeError):
    """A problem reaching or using the database, safe to show a user.

    Deliberately distinct from the driver's own exceptions: those can carry
    connection strings and credentials, and must never reach the browser
    (AGENTS.md, Security).
    """


class StagingWriteAttempt(DatabaseError):
    """Application code tried to write parser-owned staging data.

    Should be unreachable -- the SQLite backend opens staging read-only, so
    the engine itself refuses first. This exists so that if a future backend
    is ever wired up with a too-permissive database role, the failure is a
    named, obvious bug rather than a silent corruption of provenance.
    """


class Database:
    """A live connection to the staging data plus the Lapus write store."""

    def __init__(self, connection: Any, dialect: Dialect) -> None:
        self._connection = connection
        self._dialect = dialect
        # One connection guarded by a lock rather than a pool: this is a
        # single-user desktop app, and SQLite connections are not safe to
        # share across threads without it. A server backend would swap this
        # class for a pooled implementation without repositories noticing.
        self._lock = threading.RLock()

    @property
    def dialect(self) -> Dialect:
        return self._dialect

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[Row]:
        with self._lock:
            cursor = self._execute(sql, params)
            try:
                columns = [c[0] for c in cursor.description or []]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                cursor.close()

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.query_one(sql, params)
        if row is None:
            return None
        return next(iter(row.values()), None)

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Run a write. Returns the number of affected rows."""
        with self._lock:
            cursor = self._execute(sql, params)
            try:
                return cursor.rowcount
            finally:
                cursor.close()

    def insert_returning_id(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Insert one row and return its generated primary key.

        The three targets disagree about how to get this back (lastrowid,
        RETURNING, SCOPE_IDENTITY), so it is a method rather than something
        each repository open-codes.
        """
        with self._lock:
            cursor = self._execute(sql, params)
            try:
                if self._dialect.name == "sqlite":
                    return int(cursor.lastrowid)
                row = cursor.fetchone()
                if row is None:
                    raise DatabaseError("Insert did not return a generated id.")
                return int(row[0])
            finally:
                cursor.close()

    @contextmanager
    def transaction(self) -> Iterator["Database"]:
        """Group writes so a failed workflow step leaves nothing half-applied."""
        with self._lock:
            try:
                yield self
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _execute(self, sql: str, params: Sequence[Any]) -> Any:
        prepared = self._dialect.apply_paramstyle(sql)
        try:
            cursor = self._connection.cursor()
            cursor.execute(prepared, tuple(params))
            return cursor
        except sqlite3.OperationalError as exc:
            if "readonly database" in str(exc):
                raise StagingWriteAttempt(
                    "Refused a write to parser-owned staging data. "
                    "Lapus changes belong in the lapus schema."
                ) from exc
            raise DatabaseError(str(exc)) from exc


def connect(staging_url: str, lapus_url: str) -> Database:
    """Open the staging database read-only with the Lapus store attached."""
    dialect = dialect_for_url(staging_url)
    if dialect.name == "sqlite":
        from .sqlite_backend import connect_sqlite

        return connect_sqlite(staging_url, lapus_url)
    if dialect.name == "postgres":
        from .postgres_backend import connect_postgres

        return connect_postgres(staging_url)
    raise DatabaseError(
        f"The {dialect.name} backend is not implemented yet. "
        "Lapus currently runs on SQLite; PostgreSQL support is scaffolded."
    )


def staging_file_exists(url: str) -> bool:
    """Whether a SQLite staging path is actually present."""
    if "://" in url:
        return True  # server databases are checked by connecting
    return Path(url).expanduser().is_file()
