"""The central safety property: Lapus never mutates parser-owned staging data.

CODEX_START_PROMPT.md asks for tests proving that normal application operations
do not mutate any public.t01_* through t11_* table. This file does that two
ways -- by attacking the boundary directly, and by exercising the whole
application and checksumming every staging row before and after.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from lapus.catalog import load_sections
from lapus.db.engine import Database, DatabaseError
from lapus.db.sqlite_backend import staging_is_readonly
from lapus.services.change_workflow import Actor, ChangeWorkflow

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def staging_fingerprint(path: Path) -> str:
    """A checksum over every row of every parser-owned table.

    Reads through a separate read-only connection so the measurement itself
    cannot alter what it measures.
    """
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    digest = hashlib.sha256()
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name LIKE 'T%' ORDER BY name"
            )
        ]
        assert tables, "expected parser-owned tables in the staging database"
        for table in tables:
            digest.update(table.encode())
            for row in connection.execute(f"SELECT * FROM {table}"):
                digest.update(repr(row).encode())
    finally:
        connection.close()
    return digest.hexdigest()


def test_connection_reports_staging_is_readonly(database: Database) -> None:
    assert staging_is_readonly(database) is True


@pytest.mark.parametrize("section", load_sections(), ids=lambda s: s.table)
def test_every_staging_table_rejects_writes(database: Database, section) -> None:
    """Each of T01-T11 refuses UPDATE, INSERT and DELETE at the engine level.

    Not "the application declines to try" -- the connection physically cannot,
    because staging is attached read-only.
    """
    for statement in (
        f"UPDATE {section.table} SET document_id = document_id",
        f"DELETE FROM {section.table}",
        f"INSERT INTO {section.table} (document_id) VALUES (999999)",
    ):
        with pytest.raises(DatabaseError):
            database.execute(statement)


def test_t00_control_tables_also_reject_writes(database: Database) -> None:
    for table in ("t00_documents", "t00_ingestion_audit", "t00_unmapped_tables"):
        with pytest.raises(DatabaseError):
            database.execute(f"DELETE FROM {table}")


def test_full_workflow_leaves_staging_byte_identical(
    database: Database, staging_db: Path, actor: Actor, first_document_id: int
) -> None:
    """Exercise the whole application, then prove staging did not move.

    Covers the operations a user performs in a session: reading sections,
    raising a change request, adding items against both a repeating row and a
    single-record section, submitting, approving, and reading back the result.
    """
    before = staging_fingerprint(staging_db)

    workflow = ChangeWorkflow(database)
    from lapus.repositories.specs import SearchQuery, SpecRepository
    from lapus.services.specs import SpecService

    specs = SpecService(database)
    SpecRepository(database).search(SearchQuery(text="Foil"))
    specs.get_spec(first_document_id)
    specs.get_all_sections(first_document_id)

    request = workflow.create_request(actor, first_document_id, "Requalify supplier", "Trial complete")
    request_id = int(request["request_id"])

    bom = specs.get_section(first_document_id, 3)
    workflow.add_item(
        actor, request_id, 3, bom["rows"][0]["record_id"], "supplier",
        "Kestrel Substrates", False, "Qualified August 2026",
    )
    workflow.add_item(
        actor, request_id, 1, None, "structure_description",
        "48ga PET / 3.0mil LLDPE", False, "Gauge increase",
    )
    workflow.submit(actor, request_id)
    workflow.approve(actor, request_id, "Approved by QA")

    # The overlay is visible...
    section = specs.get_section(first_document_id, 3)
    assert section["rows"][0]["fields"]["supplier"]["value"] == "Kestrel Substrates"

    # ...and the staged data behind it is untouched, to the byte.
    assert staging_fingerprint(staging_db) == before


def test_approved_change_does_not_alter_the_source_value(
    database: Database, actor: Actor, first_document_id: int
) -> None:
    """An overlay adds to the staged value; it never replaces it."""
    from lapus.services.specs import SpecService

    specs = SpecService(database)
    workflow = ChangeWorkflow(database)

    original = specs.get_section(first_document_id, 3)["rows"][0]["fields"]["supplier"]["value"]

    request = workflow.create_request(actor, first_document_id, "Supplier change", None)
    request_id = int(request["request_id"])
    record_id = specs.get_section(first_document_id, 3)["rows"][0]["record_id"]
    workflow.add_item(actor, request_id, 3, record_id, "supplier", "New Supplier Co", False, None)
    workflow.submit(actor, request_id)
    workflow.approve(actor, request_id, None)

    field = specs.get_section(first_document_id, 3)["rows"][0]["fields"]["supplier"]
    assert field["value"] == "New Supplier Co"
    assert field["source_value"] == original, "the Word-source value must survive an approval"
    assert field["is_overridden"] is True
    assert field["provenance"]["original_value"] == original


# --- surviving a parser rerun ---------------------------------------------


def _reparse_document(staging_db: Path, document_id: int) -> None:
    """Do to one document exactly what the parser does on a rerun.

    From the V5.2 parser: DELETE FROM each of T01-T11 WHERE document_id = ?,
    then reinsert from the Word file. The content is identical; the surrogate
    ids are not.
    """
    connection = sqlite3.connect(staging_db)
    try:
        columns = (
            "document_id, source_table_index, source_row, row_type, basis_weight, "
            "basis_weight_range, caliper_mils, raw_material, supplier, raw_material_item_code"
        )
        rows = connection.execute(
            f"SELECT {columns} FROM T03_Bill_of_Materials WHERE document_id = ?",
            (document_id,),
        ).fetchall()
        connection.execute(
            "DELETE FROM T03_Bill_of_Materials WHERE document_id = ?", (document_id,)
        )
        placeholders = ", ".join("?" for _ in columns.split(","))
        connection.executemany(
            f"INSERT INTO T03_Bill_of_Materials ({columns}) VALUES ({placeholders})", rows
        )
        connection.commit()
    finally:
        connection.close()


def test_approved_overlay_survives_a_parser_rerun(
    tmp_path_factory, actor: Actor
) -> None:
    """AGENTS.md rule 6: a parser rerun must not destroy Lapus changes.

    It used to. The parser regenerates the surrogate id of every repeating
    row, and an overlay keyed only on target_record_id stopped matching --
    so an approved change silently reverted to the staged value with nothing
    to say it had. The change item survived; its effect did not.
    """
    import sys

    from lapus.db.engine import connect
    from lapus.db.migrations import apply_migrations
    from lapus.repositories.specs import SearchQuery, SpecRepository
    from lapus.services.change_workflow import ChangeWorkflow
    from lapus.services.specs import SpecService

    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from make_demo_db import build as build_demo

    directory = tmp_path_factory.mktemp("reparse")
    staging = directory / "Spec_Stage.db"
    build_demo(staging, force=True)

    database = connect(str(staging), str(directory / "lapus.db"))
    apply_migrations(database)
    specs, workflow = SpecService(database), ChangeWorkflow(database)

    document_id = SpecRepository(database).search(SearchQuery(limit=1))[0][0]["document_id"]
    before = specs.get_section(document_id, 3)["rows"][0]
    record_id = before["record_id"]
    staged = before["fields"]["supplier"]["source_value"]

    request = workflow.create_request(actor, document_id, "Survives reparse", None)
    request_id = int(request["request_id"])
    workflow.add_item(actor, request_id, 3, record_id, "supplier", "Northline Foil", False, None)
    workflow.submit(actor, request_id)
    workflow.approve(actor, request_id, None)

    assert specs.get_section(document_id, 3)["rows"][0]["fields"]["supplier"]["value"] == "Northline Foil"

    database.close()
    _reparse_document(staging, document_id)
    database = connect(str(staging), str(directory / "lapus.db"))
    specs = SpecService(database)

    row = specs.get_section(document_id, 3)["rows"][0]
    assert row["record_id"] != record_id, "the reparse should have regenerated the row id"
    field = row["fields"]["supplier"]
    assert field["value"] == "Northline Foil", "the approved change must survive the rerun"
    assert field["is_overridden"] is True
    assert field["source_value"] == staged
    database.close()


def test_overlay_does_not_reattach_when_the_document_changed(
    tmp_path_factory, actor: Actor
) -> None:
    """The fallback must not re-aim an approved change at different content.

    Matching by position alone would do exactly that: if the Word table was
    edited so a row now holds something else, an approved change would be
    shown over content nobody approved it against. The captured original value
    is the guard.
    """
    import sys

    from lapus.db.engine import connect
    from lapus.db.migrations import apply_migrations
    from lapus.repositories.specs import SearchQuery, SpecRepository
    from lapus.services.change_workflow import ChangeWorkflow
    from lapus.services.specs import SpecService

    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from make_demo_db import build as build_demo

    directory = tmp_path_factory.mktemp("reparse_changed")
    staging = directory / "Spec_Stage.db"
    build_demo(staging, force=True)

    database = connect(str(staging), str(directory / "lapus.db"))
    apply_migrations(database)
    specs, workflow = SpecService(database), ChangeWorkflow(database)

    document_id = SpecRepository(database).search(SearchQuery(limit=1))[0][0]["document_id"]
    record_id = specs.get_section(document_id, 3)["rows"][0]["record_id"]

    request = workflow.create_request(actor, document_id, "Will not reattach", None)
    request_id = int(request["request_id"])
    workflow.add_item(actor, request_id, 3, record_id, "supplier", "Northline Foil", False, None)
    workflow.submit(actor, request_id)
    workflow.approve(actor, request_id, None)
    database.close()

    # Reparse, but the Word document now says something different in that cell.
    connection = sqlite3.connect(staging)
    columns = (
        "document_id, source_table_index, source_row, row_type, basis_weight, "
        "basis_weight_range, caliper_mils, raw_material, supplier, raw_material_item_code"
    )
    rows = [
        list(row) for row in connection.execute(
            f"SELECT {columns} FROM T03_Bill_of_Materials WHERE document_id = ?", (document_id,)
        )
    ]
    rows[0][9 - 1] = "A Different Supplier Entirely"  # the supplier column
    connection.execute("DELETE FROM T03_Bill_of_Materials WHERE document_id = ?", (document_id,))
    connection.executemany(
        f"INSERT INTO T03_Bill_of_Materials ({columns}) "
        f"VALUES ({', '.join('?' for _ in columns.split(','))})", rows
    )
    connection.commit()
    connection.close()

    database = connect(str(staging), str(directory / "lapus.db"))
    field = SpecService(database).get_section(document_id, 3)["rows"][0]["fields"]["supplier"]
    assert field["is_overridden"] is False, (
        "an approved change must not reattach to content it was never approved against"
    )
    assert field["value"] == "A Different Supplier Entirely"
    database.close()
