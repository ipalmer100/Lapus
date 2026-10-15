"""The workflow, run against a real PostgreSQL server.

Skipped unless LAPUS_TEST_POSTGRES_URL names a database to use. That URL must
point at a PostgreSQL `Spec_Stage` holding the parser's T00-T11 staging tables;
`tools/make_test_postgres.py` builds one.

These exist because the SQLite suite could not have caught what shipped. It
tested that migrations *generate* valid DDL per dialect, which they did, while
the PostgreSQL path was broken four separate ways -- no RETURNING clause on any
INSERT, startup DDL the least-privilege role cannot execute, a literal '%' in
SQL that psycopg reads as a placeholder, and a hand-written schema script
missing a column the code writes. Every one of them needed a live server to
surface.
"""

from __future__ import annotations

import hashlib
import os

import pytest

POSTGRES_URL = os.environ.get("LAPUS_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="Set LAPUS_TEST_POSTGRES_URL to run the PostgreSQL integration tests.",
)


@pytest.fixture
def pg_database():
    from lapus.db.engine import connect
    from lapus.db.migrations import apply_migrations

    database = connect(POSTGRES_URL, "unused-on-server-backends")
    apply_migrations(database)  # verifies rather than creates
    yield database
    database.close()


@pytest.fixture
def pg_actor(pg_database):
    """An identity whose change requests are removed afterwards.

    These tests write to a shared server rather than a throwaway file, so
    without cleanup a second run inherits the first run's overlays and the
    results depend on execution order.
    """
    from lapus.services.change_workflow import Actor

    actor = Actor(email="pytest@example.com", is_approver=True, may_self_approve=True)
    yield actor
    with pg_database.transaction():
        pg_database.execute(
            "DELETE FROM lapus.change_request WHERE created_by = ?", (actor.email,)
        )


@pytest.fixture
def pg_document(pg_database) -> int:
    return int(pg_database.scalar("SELECT MIN(id) FROM t00_documents"))


def _staging_fingerprint(database) -> str:
    """Checksum every parser-owned row through the application's own connection."""
    digest = hashlib.sha256()
    tables = [
        row["table_name"]
        for row in database.query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name LIKE ANY(?) "
            "ORDER BY table_name",
            (["t0%", "t1%"],),
        )
    ]
    assert tables, "expected parser-owned tables"
    for table in tables:
        digest.update(table.encode())
        for row in database.query(f"SELECT * FROM {table} ORDER BY 1"):
            digest.update(repr(sorted(row.items())).encode())
    return digest.hexdigest()


def test_dialect_is_postgres(pg_database) -> None:
    assert pg_database.dialect.name == "postgres"


def test_role_cannot_write_staging(pg_database) -> None:
    """The read boundary on a server is the database role, not a file flag."""
    from lapus.db.postgres_backend import assert_staging_readonly

    assert assert_staging_readonly(pg_database) is True


def test_every_staging_table_rejects_writes(pg_database) -> None:
    from lapus.catalog import load_sections
    from lapus.db.engine import DatabaseError

    for section in load_sections():
        for statement in (
            f"DELETE FROM {section.table}",
            f"UPDATE {section.table} SET document_id = document_id",
        ):
            with pytest.raises(DatabaseError):
                pg_database.execute(statement)
        pg_database._connection.rollback()


def test_sql_containing_a_literal_percent_runs(pg_database) -> None:
    """psycopg reads '%' as a placeholder whenever params are passed.

    Regression test: the staging-privilege check used a LIKE pattern with a
    literal '%' and an empty params tuple, and failed startup outright.
    """
    assert pg_database.scalar("SELECT COUNT(*) FROM t00_documents WHERE filename LIKE 'S%'") >= 0


def test_insert_returns_a_generated_id(pg_database, pg_actor, pg_document) -> None:
    """Every INSERT needs RETURNING on PostgreSQL; SQLite's lastrowid is absent."""
    from lapus.repositories.changes import ChangeRepository

    repo = ChangeRepository(pg_database)
    with pg_database.transaction():
        request_id = repo.create_request(pg_document, "returning check", None, pg_actor.email)
    assert isinstance(request_id, int) and request_id > 0


def test_full_workflow_and_overlay(pg_database, pg_actor, pg_document) -> None:
    from lapus.services.change_workflow import ChangeWorkflow
    from lapus.services.specs import SpecService

    specs, workflow = SpecService(pg_database), ChangeWorkflow(pg_database)
    before = _staging_fingerprint(pg_database)

    bom = specs.get_section(pg_document, 3)
    record_id = bom["rows"][0]["record_id"]
    # The *staged* value, not the effective one. These tests run against a
    # shared server that may already carry approved overlays from an earlier
    # run, and source_value is the thing an approval never changes.
    source = bom["rows"][0]["fields"]["supplier"]["source_value"]

    request = workflow.create_request(pg_actor, pg_document, "PG workflow", "integration")
    request_id = int(request["request_id"])
    workflow.add_item(pg_actor, request_id, 3, record_id, "supplier",
                      "Integration Supplier Co", False, "test")
    workflow.submit(pg_actor, request_id)
    workflow.approve(pg_actor, request_id, "approved")

    field = specs.get_section(pg_document, 3)["rows"][0]["fields"]["supplier"]
    assert field["value"] == "Integration Supplier Co"
    assert field["source_value"] == source, "the staged value must survive approval"
    assert field["is_overridden"] is True

    assert _staging_fingerprint(pg_database) == before, "staging must be untouched"


def test_duplicate_proposal_blocked_on_single_record_section(
    pg_database, pg_actor, pg_document
) -> None:
    """The NULL-record-id case the two partial indexes exist for."""
    from lapus.services.change_workflow import ChangeWorkflow, WorkflowError

    workflow = ChangeWorkflow(pg_database)
    request = workflow.create_request(pg_actor, pg_document, "dup check", None)
    request_id = int(request["request_id"])
    workflow.add_item(pg_actor, request_id, 1, None, "customer", "First Name", False, None)
    with pytest.raises(WorkflowError):
        workflow.add_item(pg_actor, request_id, 1, None, "customer", "Second Name", False, None)


def test_clearing_a_field_round_trips(pg_database, pg_actor, pg_document) -> None:
    """clears_value was the column the shipped script forgot."""
    from lapus.services.change_workflow import ChangeWorkflow
    from lapus.services.specs import SpecService

    specs, workflow = SpecService(pg_database), ChangeWorkflow(pg_database)
    request = workflow.create_request(pg_actor, pg_document, "clear check", None)
    request_id = int(request["request_id"])
    workflow.add_item(pg_actor, request_id, 9, None, "coa_recipients", None, True, "withdrawn")
    workflow.submit(pg_actor, request_id)
    workflow.approve(pg_actor, request_id, None)

    field = specs.get_section(pg_document, 9)["rows"][0]["fields"]["coa_recipients"]
    assert field["value"] is None
    assert field["provenance"]["cleared"] is True
    assert field["source_value"] is not None, "the staged value is still shown"


def test_missing_schema_is_reported_clearly(pg_database) -> None:
    """A stale or absent lapus schema must name the remedy, not fail obscurely."""
    from lapus.db.migrations import SchemaNotInstalled, verify_schema

    class _NoSchema:
        dialect = pg_database.dialect

        def query(self, sql, params=()):
            return []

    with pytest.raises(SchemaNotInstalled, match="001_lapus_schema.sql"):
        verify_schema(_NoSchema())


def test_driver_errors_do_not_leak_the_connection(pg_database) -> None:
    """A psycopg error must not carry a DSN or a server traceback to the browser."""
    from lapus.db.engine import DatabaseError

    with pytest.raises(DatabaseError) as caught:
        pg_database.query("SELECT * FROM a_table_that_does_not_exist")
    pg_database._connection.rollback()
    message = str(caught.value).lower()
    for leak in ("password", "devpassword", "127.0.0.1", "dsn", "traceback", "psycopg"):
        assert leak not in message, f"error leaked {leak!r}: {message}"
