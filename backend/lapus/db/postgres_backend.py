"""PostgreSQL backend.

Present so the SQLite-first decision stays honest: the same repositories,
the same schema-qualified SQL, a different connection. psycopg is an optional
dependency (`pip install -e "backend[postgres]"`) and is imported only when a
postgresql:// URL is actually configured.

Unlike SQLite, the read-only staging boundary here is enforced by the database
role, not by connection flags -- grant SELECT on public and read/write on
lapus, per docs/LOCAL_SETUP.md. `assert_staging_readonly` verifies that the
role really is restricted, so a too-permissive grant is caught at startup
rather than discovered after something has already overwritten provenance.
"""

from __future__ import annotations

from .dialect import POSTGRES
from .engine import Database, DatabaseError


def connect_postgres(url: str) -> Database:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise DatabaseError(
            "PostgreSQL support needs psycopg. Install it with: "
            'pip install -e "backend[postgres]"'
        ) from exc

    try:
        connection = psycopg.connect(url, autocommit=False)
    except Exception as exc:  # pragma: no cover - needs a live server
        # Deliberately not interpolating the URL: it carries the password.
        raise DatabaseError(f"Could not connect to PostgreSQL: {type(exc).__name__}") from exc

    return Database(connection, POSTGRES)


def assert_staging_readonly(database: Database) -> bool:
    """Check the connected role cannot write parser-owned tables."""
    has_write_grant = database.scalar(
        """
        SELECT COUNT(*)
        FROM information_schema.role_table_grants
        WHERE table_schema = 'public'
          AND table_name LIKE 't__!_%' ESCAPE '!'
          AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE')
          AND grantee = CURRENT_USER
        """
    )
    return not has_write_grant
