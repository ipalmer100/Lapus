"""Creation of the Lapus-owned write model.

Mirrors db/postgres/001_lapus_schema.sql, generated per dialect so the SQLite
build and a future SQL Server build stay in step with the PostgreSQL contract
rather than drifting into three hand-maintained scripts.

These migrations only ever create objects inside the `lapus` schema. Nothing
here touches, references-with-a-foreign-key, or otherwise constrains a
parser-owned table -- on SQLite it *cannot*, since staging is attached
read-only, and on PostgreSQL the FKs to t00_documents in the reference script
are deliberately dropped: a parser rerun that deletes and reinserts documents
must not be blocked (or cascaded) by application rows. Referential integrity
against staging is checked in the service layer instead, where a missing
document is a reportable state rather than a constraint violation.
"""

from __future__ import annotations

from .dialect import Dialect
from .engine import Database, DatabaseError

SCHEMA_VERSION = 1


def _statements(dialect: Dialect) -> list[str]:
    pk = dialect.identity_pk
    ts = dialect.timestamp_type
    now = dialect.now_expression
    exists = "IF NOT EXISTS " if dialect.supports_if_not_exists_ddl else ""
    # SQLite rejects a schema-qualified REFERENCES target; PostgreSQL requires
    # one. `fk_reference` phrases it per backend.
    request_fk = dialect.fk_reference("change_request")

    statements: list[str] = []
    if dialect.creates_schema:
        statements.append("CREATE SCHEMA IF NOT EXISTS lapus")

    statements += [
        f"""
        CREATE TABLE {exists}lapus.schema_version (
            version INTEGER NOT NULL,
            applied_at {ts} NOT NULL DEFAULT {now}
        )
        """,
        f"""
        CREATE TABLE {exists}lapus.change_request (
            request_id {pk},
            document_id BIGINT NOT NULL,
            title TEXT NOT NULL,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'DRAFT'
                CHECK (status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED','CANCELLED')),
            created_by TEXT NOT NULL,
            created_at {ts} NOT NULL DEFAULT {now},
            updated_at {ts} NOT NULL DEFAULT {now},
            submitted_by TEXT,
            submitted_at {ts},
            decided_by TEXT,
            decided_at {ts},
            decision_comment TEXT
        )
        """,
        f"""
        CREATE TABLE {exists}lapus.change_item (
            item_id {pk},
            request_id BIGINT NOT NULL
                REFERENCES {request_fk}(request_id) ON DELETE CASCADE,
            target_document_id BIGINT NOT NULL,
            section_number INTEGER NOT NULL CHECK (section_number BETWEEN 1 AND 11),
            target_table TEXT NOT NULL,
            target_record_id BIGINT,
            target_field TEXT NOT NULL,
            original_value TEXT,
            proposed_value TEXT,
            -- Distinguishes "propose an empty value" from "no value proposed",
            -- which a nullable proposed_value alone cannot express. See
            -- PRODUCT_REQUIREMENTS.md: an intentional clear must be explicit.
            clears_value INTEGER NOT NULL DEFAULT 0,
            change_comment TEXT,
            created_by TEXT NOT NULL,
            created_at {ts} NOT NULL DEFAULT {now},
            updated_at {ts} NOT NULL DEFAULT {now}
        )
        """,
        f"""
        CREATE TABLE {exists}lapus.change_event (
            event_id {pk},
            request_id BIGINT NOT NULL
                REFERENCES {request_fk}(request_id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            event_comment TEXT,
            actor TEXT NOT NULL,
            created_at {ts} NOT NULL DEFAULT {now}
        )
        """,
        dialect.create_index(
            "ix_lapus_change_request_document", "change_request", "document_id"
        ),
        dialect.create_index(
            "ix_lapus_change_request_status", "change_request", "status"
        ),
        dialect.create_index("ix_lapus_change_item_request", "change_item", "request_id"),
        dialect.create_index(
            "ix_lapus_change_item_target", "change_item",
            "target_document_id, target_table, target_record_id, target_field",
        ),
        dialect.create_index(
            "ix_lapus_change_event_request", "change_event", "request_id, created_at"
        ),
        # The uniqueness rule from the PostgreSQL contract -- one proposal per
        # field per request -- as two partial indexes. target_record_id is NULL
        # for one-row-per-document sections, and in SQL a NULL never equals a
        # NULL, so a single UNIQUE constraint would silently permit duplicate
        # proposals against exactly the single-record sections. Splitting on
        # the NULL closes that gap on all three backends.
        dialect.create_index(
            "ux_lapus_change_item_row_target", "change_item",
            "request_id, target_table, target_record_id, target_field",
            unique=True, where="target_record_id IS NOT NULL",
        ),
        dialect.create_index(
            "ux_lapus_change_item_doc_target", "change_item",
            "request_id, target_table, target_field",
            unique=True, where="target_record_id IS NULL",
        ),
    ]
    return statements


# Objects every backend must have before Lapus can run.
_REQUIRED_TABLES = ("change_request", "change_item", "change_event", "schema_version")

# Columns added after the first release. Checked by name because a server
# schema is applied by an administrator from a .sql file, and an out-of-date
# script is otherwise only discovered when a user's first change request fails
# on an unknown column.
_REQUIRED_COLUMNS = {"change_item": ("clears_value",)}


class SchemaNotInstalled(DatabaseError):
    """The lapus schema is absent or out of date on a server database."""


def apply_migrations(database: Database) -> None:
    """Make sure the Lapus write model is present.

    On SQLite that means creating it: the store is a file Lapus owns, so it
    can. On a server it means *verifying* it, because the application connects
    as a least-privilege role with no DDL rights at all -- and PostgreSQL
    refuses `CREATE SCHEMA IF NOT EXISTS` for such a role even when the schema
    already exists, checking the privilege before the short-circuit. There the
    schema is installed by an administrator from db/postgres/001_lapus_schema.sql.
    """
    if not database.dialect.application_manages_schema:
        verify_schema(database)
        return

    with database.transaction():
        for statement in _statements(database.dialect):
            database.execute(statement)

        current = database.scalar("SELECT MAX(version) FROM lapus.schema_version")
        if current is None:
            database.execute(
                "INSERT INTO lapus.schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )


def verify_schema(database: Database) -> None:
    """Confirm an administrator-installed lapus schema matches what the code needs.

    Raises with the remedy named, rather than letting the gap surface later as
    a failed change request against an unknown column.
    """
    present = {
        row["table_name"]
        for row in database.query(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'lapus'"
        )
    }
    missing = [name for name in _REQUIRED_TABLES if name not in present]
    if missing:
        # An entirely absent schema is a first-time install; a schema that has
        # some tables but not others has been partially applied. Both are fixed
        # by the create script, which is a no-op for whatever already exists.
        raise SchemaNotInstalled(
            "The lapus schema is missing "
            + ", ".join(f"lapus.{name}" for name in missing)
            + ". Apply db/postgres/001_lapus_schema.sql to this database as an "
            "administrator (see docs/LOCAL_SETUP.md)."
        )

    for table, columns in _REQUIRED_COLUMNS.items():
        found = {
            row["column_name"]
            for row in database.query(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'lapus' AND table_name = ?",
                (table,),
            )
        }
        absent = [column for column in columns if column not in found]
        if absent:
            # Deliberately NOT "re-apply 001_lapus_schema.sql". That script
            # uses CREATE TABLE IF NOT EXISTS, so running it over an existing
            # schema silently does nothing and leaves the column still missing
            # -- an instruction that sends the reader round in a circle. Only
            # the ALTER-based upgrade can move an existing schema forward.
            raise SchemaNotInstalled(
                f"lapus.{table} exists but is out of date -- missing "
                + ", ".join(absent)
                + ". Apply db/postgres/002_upgrade_from_starter_kit.sql as an "
                "administrator. Re-running 001_lapus_schema.sql will NOT fix "
                "this: it skips tables that already exist. See docs/LOCAL_SETUP.md."
            )
