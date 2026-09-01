"""The database abstraction.

The project's stated constraint is that moving from SQLite to SQL Server must
be a backend swap, not a rewrite (previous_project_context.md). These tests
pin the differences the abstraction claims to cover, so a regression shows up
here rather than during the migration.
"""

from __future__ import annotations

import pytest

from lapus.db.dialect import MSSQL, POSTGRES, SQLITE, dialect_for_url
from lapus.db.migrations import _statements


@pytest.mark.parametrize("url,expected", [
    ("Spec_Stage.db", "sqlite"),
    ("/home/user/Desktop/Specs/Spec_Stage.db", "sqlite"),
    ("C:\\Users\\me\\Spec_Stage.db", "sqlite"),
    ("sqlite:///tmp/x.db", "sqlite"),
    ("postgresql://user:pw@localhost:5432/Spec_Stage", "postgres"),
    ("postgres://user:pw@host/db", "postgres"),
    ("mssql://server/Spec_Stage", "mssql"),
])
def test_url_selects_the_dialect(url: str, expected: str) -> None:
    assert dialect_for_url(url).name == expected


def test_unknown_scheme_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unrecognised"):
        dialect_for_url("mysql://host/db")


def test_placeholders_are_rewritten_per_driver() -> None:
    sql = "SELECT * FROM t WHERE a = ? AND b = ?"
    assert SQLITE.apply_paramstyle(sql) == sql
    assert POSTGRES.apply_paramstyle(sql) == "SELECT * FROM t WHERE a = %s AND b = %s"
    assert MSSQL.apply_paramstyle(sql) == sql


def test_index_ddl_puts_the_schema_where_each_backend_wants_it() -> None:
    """SQLite qualifies the index name; the others qualify the table."""
    sqlite_sql = SQLITE.create_index("ix_x", "change_request", "document_id")
    assert "lapus.ix_x ON change_request" in sqlite_sql

    postgres_sql = POSTGRES.create_index("ix_x", "change_request", "document_id")
    assert "ix_x ON lapus.change_request" in postgres_sql


def test_foreign_key_targets_are_qualified_only_where_supported() -> None:
    assert SQLITE.fk_reference("change_request") == "change_request"
    assert POSTGRES.fk_reference("change_request") == "lapus.change_request"


def test_mssql_omits_if_not_exists() -> None:
    """SQL Server has no IF NOT EXISTS on CREATE INDEX; the flag must be honoured."""
    assert "IF NOT EXISTS" not in MSSQL.create_index("ix_x", "change_request", "document_id")


@pytest.mark.parametrize("dialect", [SQLITE, POSTGRES, MSSQL], ids=lambda d: d.name)
def test_migrations_generate_for_every_dialect(dialect) -> None:
    """The Lapus schema can be expressed on all three backends."""
    statements = _statements(dialect)
    joined = " ".join(statements)
    for table in ("change_request", "change_item", "change_event", "schema_version"):
        assert f"lapus.{table}" in joined
    assert (dialect.creates_schema) == ("CREATE SCHEMA" in joined)


@pytest.mark.parametrize("dialect", [SQLITE, POSTGRES, MSSQL], ids=lambda d: d.name)
def test_migrations_never_touch_parser_owned_tables(dialect) -> None:
    """No migration may create, alter or reference a T00-T11 object.

    A foreign key from lapus.change_request to t00_documents would make a
    parser rerun -- which deletes and reinserts documents -- either fail or
    cascade away application data. The reference script's FKs are deliberately
    dropped for that reason; this test stops them coming back.
    """
    joined = " ".join(_statements(dialect)).lower()
    for staging in ("t00_", "t01_", "t02_", "t03_", "t04_", "t05_",
                    "t06_", "t07_", "t08_", "t09_", "t10_", "t11_", "v00_"):
        assert staging not in joined, f"migration referenced parser-owned {staging}*"


def test_sqlite_migration_matches_the_postgres_contract() -> None:
    """The generated schema keeps the column set the PostgreSQL contract names."""
    joined = " ".join(_statements(SQLITE))
    for column in ("target_document_id", "section_number", "target_table",
                   "target_record_id", "target_field", "original_value",
                   "proposed_value", "change_comment", "decided_by", "decided_at"):
        assert column in joined
