"""The small set of SQL differences Lapus actually cares about.

The project starts on SQLite and is expected to move to SQL Server (and is
being prototyped against PostgreSQL), so the data-access layer is written
once against this description rather than three times. Only differences the
application genuinely hits are modelled here -- deliberately not a general
SQL abstraction layer, which would cost more than the migration it is meant
to make cheap.

The single most important property is that all three targets support
schema-qualified names, so every statement Lapus writes can say
`lapus.change_request` and `t01_product_description` and mean the same thing
on each. SQLite gets there via ATTACH (see sqlite_backend.py).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dialect:
    """How to phrase the handful of things that vary between backends."""

    name: str

    # Parameter marker. SQLite/pyodbc use `?`; psycopg uses `%s`. Repository
    # code always writes `?` and the backend rewrites if needed, so queries
    # stay readable and there is exactly one place that knows the difference.
    paramstyle: str

    # Case-insensitive substring match. PostgreSQL needs ILIKE; SQLite's LIKE
    # is already case-insensitive for ASCII; SQL Server's collation normally
    # is too.
    ilike_operator: str

    # Auto-incrementing primary key column definition.
    identity_pk: str

    # Timestamp column type and "now" expression.
    timestamp_type: str
    now_expression: str

    # Whether the backend needs the `lapus` schema created explicitly. SQLite
    # gets its schema by attaching a second database file instead.
    creates_schema: bool

    # Where the schema name goes in a CREATE INDEX. SQLite qualifies the index
    # *name* (`CREATE INDEX lapus.ix_x ON change_request(...)`) and rejects a
    # qualified table there; PostgreSQL and SQL Server do exactly the reverse.
    # Verified against SQLite 3: `ON lapus.change_request` is a syntax error.
    schema_qualifies_index_name: bool

    # Whether a REFERENCES clause may name the schema. SQLite foreign keys are
    # always within one database and reject a qualified target, so the
    # reference is written bare and resolves inside the attached `lapus` file.
    schema_qualifies_fk_target: bool

    # SQL Server has no `IF NOT EXISTS` on CREATE TABLE/INDEX; it needs
    # `IF NOT EXISTS (SELECT ...)` guards instead. Flagged rather than silently
    # generating DDL that would not run there.
    supports_if_not_exists_ddl: bool

    def qualified(self, table: str) -> str:
        """`lapus.change_request` -- how the table is named in a query."""
        return f"lapus.{table}"

    def fk_reference(self, table: str) -> str:
        """How to name a `lapus` table inside a REFERENCES clause."""
        return self.qualified(table) if self.schema_qualifies_fk_target else table

    def create_index(self, name: str, table: str, columns: str, *,
                     unique: bool = False, where: str | None = None) -> str:
        """A CREATE INDEX statement on a `lapus` table, phrased for this backend."""
        unique_sql = "UNIQUE " if unique else ""
        exists_sql = "IF NOT EXISTS " if self.supports_if_not_exists_ddl else ""
        if self.schema_qualifies_index_name:
            target = f"{exists_sql}lapus.{name} ON {table}"
        else:
            target = f"{exists_sql}{name} ON {self.qualified(table)}"
        statement = f"CREATE {unique_sql}INDEX {target}({columns})"
        if where:
            statement += f" WHERE {where}"
        return statement

    def apply_paramstyle(self, sql: str) -> str:
        """Rewrite `?` markers if this backend expects something else.

        Only called on SQL that this codebase authored, and only rewrites the
        marker character -- user input never reaches here, it travels as bound
        parameters (see AGENTS.md rule 10).
        """
        if self.paramstyle == "qmark":
            return sql
        if self.paramstyle == "format":
            return sql.replace("?", "%s")
        raise ValueError(f"Unsupported paramstyle: {self.paramstyle}")


SQLITE = Dialect(
    name="sqlite",
    paramstyle="qmark",
    ilike_operator="LIKE",
    identity_pk="INTEGER PRIMARY KEY AUTOINCREMENT",
    timestamp_type="TEXT",
    now_expression="CURRENT_TIMESTAMP",
    creates_schema=False,
    schema_qualifies_index_name=True,
    schema_qualifies_fk_target=False,
    supports_if_not_exists_ddl=True,
)

POSTGRES = Dialect(
    name="postgres",
    paramstyle="format",
    ilike_operator="ILIKE",
    identity_pk="BIGSERIAL PRIMARY KEY",
    timestamp_type="TIMESTAMPTZ",
    now_expression="CURRENT_TIMESTAMP",
    creates_schema=True,
    schema_qualifies_index_name=False,
    schema_qualifies_fk_target=True,
    supports_if_not_exists_ddl=True,
)

MSSQL = Dialect(
    name="mssql",
    paramstyle="qmark",
    ilike_operator="LIKE",
    identity_pk="BIGINT IDENTITY(1,1) PRIMARY KEY",
    timestamp_type="DATETIMEOFFSET",
    now_expression="SYSUTCDATETIME()",
    creates_schema=True,
    schema_qualifies_index_name=False,
    schema_qualifies_fk_target=True,
    supports_if_not_exists_ddl=False,
)

_BY_NAME = {d.name: d for d in (SQLITE, POSTGRES, MSSQL)}


def dialect_for_url(url: str) -> Dialect:
    """Pick the dialect a connection string implies.

    A string with no scheme is a filesystem path, i.e. SQLite -- which keeps
    the common case (`Spec_Stage.db`) free of URL ceremony.
    """
    if "://" not in url:
        return SQLITE
    scheme = url.split("://", 1)[0].lower()
    if scheme in {"sqlite", "file"}:
        return SQLITE
    if scheme in {"postgresql", "postgres"}:
        return POSTGRES
    if scheme in {"mssql", "sqlserver"}:
        return MSSQL
    raise ValueError(
        f"Unrecognised database URL scheme '{scheme}'. "
        "Expected a filesystem path (SQLite), postgresql://, or mssql://."
    )


def dialect_by_name(name: str) -> Dialect:
    try:
        return _BY_NAME[name]
    except KeyError:
        raise ValueError(f"Unknown dialect '{name}'") from None
