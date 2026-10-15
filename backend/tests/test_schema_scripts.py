"""The checked-in .sql scripts must match what the code expects.

On a server backend Lapus does not create its own schema -- an administrator
applies db/postgres/001_lapus_schema.sql. That makes the script part of the
contract, and a script that drifts from the code is invisible until a user's
first change request fails against a column that was never created.

That is exactly what happened: the original hand-written script was missing
`clears_value`, missing `lapus.schema_version`, carried foreign keys into
`public.t00_documents`, and used a plain UNIQUE constraint where NULL record
ids need two partial indexes. These tests make that class of drift impossible
to commit.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EMITTER = REPO_ROOT / "tools" / "emit_schema_sql.py"
POSTGRES_SCRIPT = REPO_ROOT / "db" / "postgres" / "001_lapus_schema.sql"


def test_postgres_script_matches_the_code() -> None:
    """Fails if db/postgres/001_lapus_schema.sql is out of date."""
    result = subprocess.run(
        [sys.executable, str(EMITTER), "--dialect", "postgres", "--check"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"{POSTGRES_SCRIPT} is out of date with backend/lapus/db/migrations.py.\n"
        "Regenerate it: python tools/emit_schema_sql.py --dialect postgres\n"
        f"{result.stderr}"
    )


def test_postgres_script_creates_every_column_the_code_writes() -> None:
    """Every column the repositories insert must exist in the script."""
    script = POSTGRES_SCRIPT.read_text(encoding="utf-8")
    changes = (REPO_ROOT / "backend" / "lapus" / "repositories" / "changes.py").read_text()

    # The column that was missing and broke every write on PostgreSQL.
    assert "clears_value" in script
    assert "clears_value" in changes

    for column in (
        "target_document_id", "section_number", "target_table", "target_record_id",
        "target_field", "original_value", "proposed_value", "change_comment",
        "submitted_by", "decided_by", "decision_comment",
    ):
        assert column in script, f"{column} missing from the PostgreSQL script"


def _executable_sql(path: Path) -> str:
    """The script with comments stripped.

    The header explains at length *why* there are no foreign keys into
    public.t00_documents, so a naive substring search over the whole file
    matches the explanation and not the DDL.
    """
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        code = line.split("--", 1)[0]
        if code.strip():
            lines.append(code)
    return "\n".join(lines).lower()


def test_postgres_script_has_no_foreign_keys_into_staging() -> None:
    """A FK to t00_documents would break the parser's own rerun.

    The parser deletes and reinserts documents. ON DELETE RESTRICT would block
    that; ON DELETE CASCADE would silently destroy user change requests. Either
    way the application must not constrain parser-owned data.
    """
    sql = _executable_sql(POSTGRES_SCRIPT)
    for line in sql.splitlines():
        if "references" in line:
            assert "lapus." in line, f"foreign key leaves the lapus schema: {line.strip()}"
    for staging in ("t00_", "t01_", "t03_", "t11_", "v00_"):
        assert staging not in sql, f"script references parser-owned {staging}*"


def test_postgres_script_uses_partial_unique_indexes() -> None:
    """NULL record ids need two indexes, not one UNIQUE constraint.

    target_record_id is NULL for single-record sections, and a NULL never
    equals a NULL, so a plain UNIQUE would permit duplicate proposals against
    exactly those sections.
    """
    script = POSTGRES_SCRIPT.read_text(encoding="utf-8")
    assert "WHERE target_record_id IS NOT NULL" in script
    assert "WHERE target_record_id IS NULL" in script


def test_script_is_marked_generated() -> None:
    assert "GENERATED FILE" in POSTGRES_SCRIPT.read_text(encoding="utf-8")
