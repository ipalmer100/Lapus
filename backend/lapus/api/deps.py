"""Shared application state and request-scoped dependencies.

One database connection is opened at startup and shared, matching the
single-user desktop model. `get_actor` is the seam where real authentication
goes later: everything downstream already takes identity from an Actor rather
than trusting anything in a request body.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..db.engine import Database, connect
from ..db.migrations import apply_migrations
from ..db.sqlite_backend import staging_is_readonly
from ..services.change_workflow import Actor
from ..settings import Settings, load_settings

_state: dict[str, Any] = {"database": None, "settings": None, "staging_readonly": None}


def startup(settings: Settings | None = None) -> Database:
    """Open the database, create the Lapus schema, verify the read-only boundary."""
    settings = settings or load_settings()
    database = connect(settings.database_url, settings.lapus_database_url)
    apply_migrations(database)

    readonly = True
    if database.dialect.name == "sqlite":
        readonly = staging_is_readonly(database)
    elif database.dialect.name == "postgres":  # pragma: no cover - needs a server
        from ..db.postgres_backend import assert_staging_readonly

        readonly = assert_staging_readonly(database)

    _state["database"] = database
    _state["settings"] = settings
    _state["staging_readonly"] = readonly
    return database


def shutdown() -> None:
    database = _state.get("database")
    if database is not None:
        database.close()
    _state.update({"database": None, "settings": None, "staging_readonly": None})


def get_database() -> Database:
    database = _state.get("database")
    if database is None:
        raise HTTPException(status_code=503, detail="The specification database is not open.")
    return database


def get_settings() -> Settings:
    settings = _state.get("settings")
    if settings is None:
        raise HTTPException(status_code=503, detail="Lapus is not configured.")
    return settings


def staging_is_protected() -> bool:
    return bool(_state.get("staging_readonly"))


def get_actor() -> Actor:
    """Who the request is from.

    Single configured identity for the POC. When SSO arrives this reads the
    authenticated principal instead; no caller changes.
    """
    settings = get_settings()
    return Actor(
        email=settings.dev_user_email,
        is_approver=settings.dev_user_is_approver,
        may_self_approve=settings.allow_self_approval,
    )


def require_approver() -> Actor:
    actor = get_actor()
    if not actor.is_approver:
        raise HTTPException(
            status_code=403, detail="You are not authorised to use the approvals area."
        )
    return actor
