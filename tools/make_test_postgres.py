"""Build a PostgreSQL Spec_Stage for development and integration testing.

Creates the parser-owned T00-T11 staging schema, loads it with the demo corpus,
applies the Lapus schema, and creates the least-privilege application role --
the same shape docs/LOCAL_SETUP.md prescribes for a real deployment, so what
the tests run against matches what is actually deployed.

The staging DDL is lifted from the V5.2 parser itself rather than retyped, so
this cannot drift from what the parser really creates.

Usage:
    python tools/make_test_postgres.py --admin-url postgresql://postgres@127.0.0.1:5433/postgres

Then:
    export LAPUS_TEST_POSTGRES_URL=postgresql://lapus_app:<password>@127.0.0.1:5433/Spec_Stage
    pytest backend/tests/test_postgres_integration.py
"""

from __future__ import annotations

import argparse
import ast
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PARSER = REPO_ROOT / "reference" / "word_specs_to_postgres_v5_2_corpus_aware_Spec_Stage.py"
LAPUS_SCHEMA = REPO_ROOT / "db" / "postgres" / "001_lapus_schema.sql"
DEMO_SQLITE = REPO_ROOT / "Spec_Stage.db"

# Identity columns whose sequences must be re-synced after rows are inserted
# with explicit ids copied from the demo database.
_SEQUENCE_TABLES = [
    "t00_documents", "t00_ingestion_audit", "t00_unmapped_tables",
    "t00_ingestion_errors", "t03_bill_of_materials",
    "t04_secondary_approved_materials", "t05_process_routing",
    "t06_physical_attributes_testing", "t11_revision_history",
]


def parser_sql(name: str) -> str:
    """Lift one SQL constant out of the parser without importing it.

    The parser imports python-docx at module scope, which is irrelevant here
    and need not be installed; reading the literal from the AST keeps the
    parser as the single source of truth for the staging DDL regardless.
    """
    tree = ast.parse(PARSER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise SystemExit(f"{name} not found in {PARSER.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url", required=True,
                        help="A superuser connection, e.g. postgresql://postgres@127.0.0.1:5433/postgres")
    parser.add_argument("--database", default="Spec_Stage")
    parser.add_argument("--role", default="lapus_app")
    parser.add_argument("--password", default="devpassword",
                        help="Development only. Never use a real credential here.")
    parser.add_argument("--demo-db", type=Path, default=DEMO_SQLITE)
    args = parser.parse_args()

    try:
        import psycopg
    except ImportError:
        raise SystemExit('psycopg is needed. Install it: pip install -e "backend[postgres]"')

    if not args.demo_db.is_file():
        raise SystemExit(
            f"{args.demo_db} not found. Generate it first: python tools/make_demo_db.py"
        )

    base = args.admin_url.rsplit("/", 1)[0]
    target_url = f"{base}/{args.database}"

    with psycopg.connect(args.admin_url, autocommit=True) as admin:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (args.database,)
        ).fetchone()
        if not exists:
            admin.execute(f'CREATE DATABASE "{args.database}"')
            print(f"created database {args.database}")

    with psycopg.connect(target_url, autocommit=True) as conn:
        conn.execute(parser_sql("POSTGRES_SCHEMA_SQL"))
        conn.execute(parser_sql("POSTGRES_VIEW_SQL"))
        print("staging schema and V00 views created from the parser's own SQL")

        _load_demo_rows(conn, args.demo_db)

        conn.execute(LAPUS_SCHEMA.read_text(encoding="utf-8"))
        print("lapus schema applied from db/postgres/001_lapus_schema.sql")

        _create_role(conn, args.role, args.password, args.database)

    print(
        "\nReady. To run the integration tests:\n"
        f"  export LAPUS_TEST_POSTGRES_URL={base.replace('postgresql://postgres', f'postgresql://{args.role}:{args.password}')}/{args.database}\n"
        "  pytest backend/tests/test_postgres_integration.py"
    )


def _load_demo_rows(conn, demo_db: Path) -> None:
    lite = sqlite3.connect(demo_db)
    lite.row_factory = sqlite3.Row
    tables = [
        row[0] for row in lite.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'T%' "
            "AND name NOT LIKE '%sequence%' ORDER BY name"
        )
    ]
    for table in tables:
        rows = [dict(row) for row in lite.execute(f"SELECT * FROM {table}")]
        if not rows:
            continue
        columns = list(rows[0])
        placeholders = ", ".join(["%s"] * len(columns))
        conn.cursor().executemany(
            f'INSERT INTO {table.lower()} ({", ".join(columns)}) VALUES ({placeholders})',
            [tuple(row[column] for column in columns) for row in rows],
        )
        print(f"  {table.lower():38} {len(rows):>4} rows")
    lite.close()

    for table in _SEQUENCE_TABLES:
        conn.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
        )
    print("identity sequences re-synced")


def _create_role(conn, role: str, password: str, database: str) -> None:
    """Create the application role with exactly the grants LOCAL_SETUP.md names.

    Deliberately no CREATE on the database or the schema: Lapus must not be
    able to run DDL, and the integration tests rely on that to prove the
    read boundary is real.
    """
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
    if not exists:
        conn.execute(f"CREATE ROLE {role} LOGIN PASSWORD %s", (password,))
    conn.execute(f'GRANT CONNECT ON DATABASE "{database}" TO {role}')
    conn.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    conn.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}")
    conn.execute(f"GRANT USAGE ON SCHEMA lapus TO {role}")
    conn.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA lapus TO {role}")
    conn.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA lapus TO {role}")
    print(f"role {role} created with read-only access to public, read/write on lapus")


if __name__ == "__main__":
    main()
