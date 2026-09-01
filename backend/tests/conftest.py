"""Shared fixtures.

Every test runs against a real generated staging database rather than mocks:
the read-only boundary, the ATTACH, and the cross-schema overlay joins are the
things most worth testing, and none of them exist against a fake.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from make_demo_db import build as build_demo_db  # noqa: E402

from lapus.api import deps  # noqa: E402
from lapus.db.engine import Database, connect  # noqa: E402
from lapus.db.migrations import apply_migrations  # noqa: E402
from lapus.services.change_workflow import Actor, ChangeWorkflow  # noqa: E402
from lapus.settings import Settings  # noqa: E402


@pytest.fixture(scope="session")
def staging_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A generated Spec_Stage.db, built once for the whole session.

    Session-scoped and never written to -- the app opens it read-only, which is
    exactly what the tests are here to confirm.
    """
    path = tmp_path_factory.mktemp("staging") / "Spec_Stage.db"
    build_demo_db(path, force=True)
    return path


@pytest.fixture
def settings(staging_db: Path, tmp_path: Path) -> Settings:
    return Settings(
        database_url=str(staging_db),
        lapus_database_url=str(tmp_path / "lapus.db"),
        dev_user_email="tester@example.com",
        dev_user_is_approver=True,
        allow_self_approval=True,
        host="127.0.0.1",
        port=8770,
        frontend_origin="http://localhost:5173",
    )


@pytest.fixture
def database(settings: Settings) -> Iterator[Database]:
    db = connect(settings.database_url, settings.lapus_database_url)
    apply_migrations(db)
    yield db
    db.close()


@pytest.fixture
def actor() -> Actor:
    return Actor(email="tester@example.com", is_approver=True, may_self_approve=True)


@pytest.fixture
def author() -> Actor:
    """A second identity, for the rules that turn on who is acting."""
    return Actor(email="author@example.com", is_approver=False)


@pytest.fixture
def workflow(database: Database) -> ChangeWorkflow:
    return ChangeWorkflow(database)


@pytest.fixture
def client(settings: Settings) -> Iterator[object]:
    """A TestClient wired to the fixture database rather than the environment."""
    from fastapi.testclient import TestClient

    from lapus.api.app import create_app

    app = create_app()

    # create_app()'s lifespan reads settings from the environment; point the
    # startup at the fixture settings instead by pre-opening the connection.
    deps.shutdown()
    deps.startup(settings)
    app.state.startup_error = None

    class _KeepOpen:
        """Stops the app's own lifespan from replacing or closing our database."""

        def __enter__(self): return None
        def __exit__(self, *_): return False

    original_startup, original_shutdown = deps.startup, deps.shutdown
    deps.startup = lambda *_a, **_k: deps.get_database()  # type: ignore[assignment]
    deps.shutdown = lambda: None  # type: ignore[assignment]
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        deps.startup, deps.shutdown = original_startup, original_shutdown
        original_shutdown()


@pytest.fixture
def first_document_id(database: Database) -> int:
    return int(database.scalar("SELECT MIN(id) FROM t00_documents"))
