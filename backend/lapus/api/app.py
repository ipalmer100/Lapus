"""The FastAPI application: routes, error handling, and serving the built UI.

The frontend is served by this same process on the same port, which is what
lets the packaged executable be one thing a user double-clicks rather than a
backend and a frontend they have to start separately.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..catalog import UnknownTarget
from ..db.engine import DatabaseError, StagingWriteAttempt
from ..settings import load_settings
from . import admin, change_requests, deps, specs


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = load_settings()
    try:
        deps.startup(settings)
    except DatabaseError as exc:
        # Startup failures are held rather than raised so the app still serves
        # its UI and can explain what is wrong. A packaged app that refuses to
        # start gives a business user a closing console window and nothing else.
        app.state.startup_error = str(exc)
    else:
        app.state.startup_error = None
    yield
    deps.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Lapus",
        summary="Specification management over parser-staged manufacturing data.",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.state.startup_error = None

    settings = load_settings()
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        # Only the Vite dev server. In the packaged app the UI is same-origin,
        # so this matters for development alone.
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(StagingWriteAttempt)
    async def _staging_write(_: Request, exc: StagingWriteAttempt) -> JSONResponse:
        # Should be unreachable; if it ever fires it is a bug worth a loud,
        # specific response rather than a generic 500.
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(DatabaseError)
    async def _database_error(_: Request, exc: DatabaseError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(UnknownTarget)
    async def _unknown_target(_: Request, exc: UnknownTarget) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    app.include_router(specs.router)
    app.include_router(change_requests.router)
    app.include_router(admin.router)

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, Any]:
        """Whether the app is usable, and on what.

        The UI calls this first: if the database could not be opened it shows
        the reason and the path it tried, instead of an empty search screen.
        """
        error = getattr(app.state, "startup_error", None)
        if error:
            return {
                "status": "unavailable",
                "detail": error,
                "database": None,
                "user": None,
            }
        database = deps.get_database()
        current = deps.get_settings()
        actor = deps.get_actor()
        return {
            "status": "ok",
            "detail": None,
            "database": {
                "dialect": database.dialect.name,
                "staging_source": str(current.staging_path or "server database"),
                "staging_is_readonly": deps.staging_is_protected(),
                "document_count": database.scalar("SELECT COUNT(*) FROM t00_documents"),
            },
            "user": {"email": actor.email, "is_approver": actor.is_approver},
        }

    _mount_frontend(app)
    return app


def _frontend_dist() -> Path | None:
    """The built UI, in a source checkout or inside a frozen bundle."""
    frozen_base = getattr(sys, "_MEIPASS", None)
    candidate = (
        Path(frozen_base) / "frontend_dist"
        if frozen_base
        else Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"
    )
    return candidate if candidate.is_dir() else None


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built frontend at the root, if it has been built.

    Mounted last so it never shadows /api. Absent during backend-only
    development, where Vite serves the UI on its own port instead.
    """
    dist = _frontend_dist()
    if dist is not None:
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")


app = create_app()
