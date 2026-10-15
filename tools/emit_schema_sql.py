"""Emit the Lapus schema as a .sql script for a server backend.

On SQLite, Lapus creates its own schema at startup. On PostgreSQL and SQL
Server it cannot -- the application role has no DDL rights by design -- so an
administrator applies a script instead. That script must say exactly what
`db/migrations.py` expects, and the way to guarantee it is to generate it from
the same code rather than maintain a second copy by hand.

An earlier hand-maintained script had drifted badly: it was missing the
`clears_value` column the application writes on every change item, missing
`lapus.schema_version` entirely, carried foreign keys into `public.t00_documents`
that a parser rerun would trip over, and used a plain UNIQUE constraint where
NULL record ids need two partial indexes. None of that was visible until the
code met a real server.

Usage:
    python tools/emit_schema_sql.py --dialect postgres
    python tools/emit_schema_sql.py --dialect postgres --check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from lapus.db.dialect import dialect_by_name  # noqa: E402
from lapus.db.migrations import SCHEMA_VERSION, _statements  # noqa: E402

DEFAULT_OUTPUT = {
    "postgres": REPO_ROOT / "db" / "postgres" / "001_lapus_schema.sql",
    "mssql": REPO_ROOT / "db" / "mssql" / "001_lapus_schema.sql",
}

HEADER = """\
-- Lapus application-owned schema for {name}.
--
-- GENERATED FILE -- do not edit by hand.
-- Regenerate with:  python tools/emit_schema_sql.py --dialect {dialect}
--
-- Generated from backend/lapus/db/migrations.py, which is the single source of
-- truth for the Lapus write model. tests/test_schema_scripts.py fails if this
-- file and that module disagree, so the two cannot drift apart.
--
-- Apply this as a database administrator. The Lapus application role must NOT
-- have DDL rights (see docs/LOCAL_SETUP.md): it connects with SELECT on the
-- parser-owned public schema and read/write only on lapus.
--
-- This script does not create, alter or reference any parser-owned T00-T11
-- object. In particular there are deliberately NO foreign keys from lapus
-- tables to public.t00_documents: the parser deletes and reinserts documents
-- on every rerun, and such a constraint would either block that rerun or
-- cascade user change requests away with it. Referential integrity against
-- staging is enforced in the service layer, where a missing document is a
-- reportable state rather than a constraint violation.
"""


def render(dialect_name: str) -> str:
    dialect = dialect_by_name(dialect_name)
    parts = [HEADER.format(name=_pretty(dialect_name), dialect=dialect_name)]
    for statement in _statements(dialect):
        parts.append(_tidy(statement) + ";")
    parts.append(
        "-- Record the schema version the application expects.\n"
        f"INSERT INTO lapus.schema_version (version)\n"
        f"SELECT {SCHEMA_VERSION}\n"
        "WHERE NOT EXISTS (SELECT 1 FROM lapus.schema_version);"
    )
    return "\n\n".join(parts) + "\n"


def _pretty(name: str) -> str:
    return {"postgres": "PostgreSQL", "mssql": "SQL Server"}.get(name, name)


def _tidy(statement: str) -> str:
    """Strip the uniform indentation the Python triple-quoted strings carry."""
    lines = [line.rstrip() for line in statement.strip("\n").rstrip().splitlines()]
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    shift = min(indents) if indents else 0
    return "\n".join(line[shift:] if line.strip() else "" for line in lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dialect", default="postgres", choices=sorted(DEFAULT_OUTPUT))
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--check", action="store_true",
        help="Exit non-zero if the file on disk differs from what would be generated.",
    )
    args = parser.parse_args()

    output = args.output or DEFAULT_OUTPUT[args.dialect]
    rendered = render(args.dialect)

    if args.check:
        current = output.read_text(encoding="utf-8") if output.is_file() else ""
        if current != rendered:
            print(f"{output} is out of date. Regenerate it:", file=sys.stderr)
            print(f"  python tools/emit_schema_sql.py --dialect {args.dialect}", file=sys.stderr)
            raise SystemExit(1)
        print(f"{output} is up to date.")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {output} ({len(rendered.splitlines())} lines)")


if __name__ == "__main__":
    main()
