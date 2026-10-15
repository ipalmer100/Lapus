# Local Development Setup

Lapus runs on SQLite today and is built to move to SQL Server (with PostgreSQL
scaffolded in between). Start with the SQLite path unless you specifically need
one of the others.

## Prerequisites

- Python 3.11+
- Node.js 20+ (LTS)
- Git

The parser may use a different installed Python; Lapus does not need to share
its virtual environment.

### A note on Windows PowerShell

The command blocks below are POSIX shell. On Windows PowerShell three things
differ, and all three produce confusing errors rather than obvious ones:

| POSIX | Windows PowerShell |
| --- | --- |
| `VAR=value command` | `$env:VAR = "value"` on its own line, then the command |
| `a && b` | one command per line (`&&` is a parse error before PowerShell 7) |
| `.venv/bin/pip` | `.venv\Scripts\python.exe -m pip` |

Prefer `python.exe -m pip` over `pip.exe`. The latter is a separate shim
executable, and a managed Windows machine may refuse to run a freshly created
`.exe` from a user profile -- which surfaces as
`Program 'pip.exe' failed to run: Access is denied`, not as a policy message.
Going through the interpreter sidesteps the shim entirely. The same trick is
why `packaging/build_windows_exe.bat` calls `python -m PyInstaller`.

---

## SQLite (the default)

### 1. Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e "backend[dev]"
cd frontend && npm install && npm run build && cd ..
```

### 2. Point it at a specification database

Either use the real `Spec_Stage.db` the parser produced, or generate a sample
one:

```bash
.venv/bin/python tools/make_demo_db.py
```

Lapus finds the database without configuration if it is called
`Spec_Stage.db` and sits in the working directory or in `Desktop/Specs/`.
Otherwise set `LAPUS_DATABASE_URL`.

### 3. Run

```bash
LAPUS_DATABASE_URL=Spec_Stage.db .venv/bin/python -m lapus.desktop
```

The API and the built UI are both served on http://127.0.0.1:8770/.

For frontend work with hot reload, run the two halves separately:

```bash
LAPUS_DATABASE_URL=Spec_Stage.db .venv/bin/python -m uvicorn lapus.api.app:app --port 8770 --reload
cd frontend && npm run dev     # http://localhost:5173, proxies /api
```

### 4. There is no migration step

Lapus creates `lapus.db` on first run and attaches it as schema `lapus`. The
staging database is opened read-only and is never modified, so it needs no
migration, no schema change and no permissions work.

By default the Lapus store goes to a per-user application data folder
(`%APPDATA%\Lapus\` on Windows, `~/.local/share/Lapus/` on Linux,
`~/Library/Application Support/Lapus/` on macOS), deliberately not beside the
staging file — that may live on a read-only share, and replacing it after a
parser run must not disturb change requests. Override with
`LAPUS_APP_DATABASE_URL`.

### 5. Verify

```bash
curl http://127.0.0.1:8770/api/health
```

`staging_is_readonly` must be `true`. If it is not, the boundary is not in
force and change requests should not be trusted — check that
`LAPUS_APP_DATABASE_URL` is not pointing at the staging database.

---

## PostgreSQL

The path to use if your V5.2 parser writes to a PostgreSQL `Spec_Stage`.
Verified end to end against PostgreSQL 16, including the full change workflow
and a proof that staging stays untouched.

### 1. Create the Lapus schema

Run `db/postgres/001_lapus_schema.sql` against `Spec_Stage` **as an
administrator**, then optionally `db/postgres/002_read_model_views.sql`.

This step is not optional and Lapus will not do it for you. On SQLite the
application creates its own schema, because the store is a file it owns. On a
server it connects as a least-privilege role with no DDL rights at all, and
PostgreSQL refuses `CREATE SCHEMA IF NOT EXISTS` for such a role *even when the
schema already exists* -- it checks the privilege before the short-circuit. So
Lapus verifies the schema at startup instead, and tells you exactly what is
missing if it is absent or out of date.

`001_lapus_schema.sql` is generated from `backend/lapus/db/migrations.py` and
must not be hand-edited. To regenerate it after a schema change:

```bash
python tools/emit_schema_sql.py --dialect postgres
```

`backend/tests/test_schema_scripts.py` fails if the checked-in script and the
code disagree.

### 2. Create a restricted application role

The read boundary here is the database role, not a connection flag. Grant only
what Lapus needs:

```sql
CREATE ROLE lapus_app LOGIN PASSWORD 'CHANGE_ME';
GRANT CONNECT ON DATABASE "Spec_Stage" TO lapus_app;

GRANT USAGE ON SCHEMA public TO lapus_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO lapus_app;

GRANT USAGE ON SCHEMA lapus TO lapus_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA lapus TO lapus_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA lapus TO lapus_app;
```

Do **not** grant INSERT, UPDATE or DELETE on `public`. Lapus checks at startup
that the connected role lacks them and reports `staging_is_readonly: false` on
`/api/health` if it does not.

### 3. Install the extra and configure

```bash
.venv/bin/pip install -e "backend[postgres]"
export LAPUS_DATABASE_URL="postgresql://lapus_app:YOUR_PASSWORD@localhost:5432/Spec_Stage"
```

Never commit a real password. `.env` is gitignored.

### 4. Verify

```bash
curl http://127.0.0.1:8770/api/health
```

`"dialect": "postgres"` and `"staging_is_readonly": true` together mean the
role is correctly restricted. If `staging_is_readonly` is false, the role has
INSERT/UPDATE/DELETE on `public` that it should not have -- fix the grants
before trusting anything.

### 5. Integration tests against a real server

The SQLite suite cannot catch backend-specific breakage, so there is a separate
suite that runs only when you point it at a live database:

```bash
# Build a throwaway Spec_Stage with the parser's staging schema, the demo
# corpus, the lapus schema and the restricted role:
python tools/make_test_postgres.py --admin-url postgresql://postgres@localhost:5432/postgres

export LAPUS_TEST_POSTGRES_URL=postgresql://lapus_app:devpassword@localhost:5432/Spec_Stage
pytest backend/tests/test_postgres_integration.py
```

Without `LAPUS_TEST_POSTGRES_URL` those tests skip, so the normal suite still
runs anywhere.

---

## SQL Server

Not implemented yet. `backend/lapus/db/dialect.py` describes the differences
and `backend/tests/test_dialects.py` checks the Lapus schema generates for it;
what remains is a `pyodbc` connection function alongside the other backends. No
repository or service code needs to change.

---

## Tests

```bash
.venv/bin/python -m pytest backend/tests -q
cd frontend && npx tsc -b
```

The suite builds its own staging database, so it needs no configuration and
never touches yours.
