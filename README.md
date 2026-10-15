# Lapus

A specification management application over the staging database the V5.2
corpus-aware parser produces from ~14,000 Word product specifications.

```text
Word specifications
  -> V5.2 corpus-aware parser
  -> Spec_Stage  (T00-T11 staging tables)
  -> Lapus API
  -> Lapus web UI  (packaged as a desktop executable)
```

Lapus lets people **find** a specification without opening Word, **read** all
eleven sections in the document's own order, and **propose, review and approve
changes** to specification data — without ever modifying the parser-owned
staging tables.

## The one rule everything else follows

`t01_*` through `t11_*` belong to the parser. It deletes and reinserts them
whenever it re-reads a document. An application edit written there would be
destroyed by the next parser run, and would take the record of what the Word
document actually said with it.

So Lapus never writes to them. Approved changes live in an application-owned
`lapus` schema and are rendered **over** the staged values, with the source
value and full provenance always visible beside them.

This is enforced by the connection, not by convention. On SQLite the staging
database is opened `mode=ro` and the Lapus store is attached as schema
`lapus`; SQLite applies open flags per attached database, so a write to a
staging table fails inside the engine. `backend/tests/test_staging_readonly.py`
proves it both directly and by checksumming every staged row before and after a
full session.

See [docs/adr/0001-staging-overlay-model.md](docs/adr/0001-staging-overlay-model.md)
for why, and what it costs.

## Running it

### As a desktop app (what a business user gets)

Build once on a Windows machine, then double-click `Lapus.exe`. No Python, no
Node, no terminal. See [packaging/README.md](packaging/README.md).

### From source

Prerequisites: Python 3.11+, Node.js 20+, Git.

**Windows (PowerShell)** — note that `cmd`-style `set VAR=value` and bash-style
`a && b` do not work in Windows PowerShell 5.1; the equivalents are below.

```powershell
git clone https://github.com/ipalmer100/Lapus.git
cd Lapus

# 1. Backend. Go through python.exe rather than the pip.exe shim: the shim is
#    a separate executable, and some managed Windows machines block running
#    newly created .exe files out of a user profile.
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e "backend[dev,postgres]"

# 2. A database to point at. Skip this if you have a real Spec_Stage.
.venv\Scripts\python.exe tools\make_demo_db.py

# 3. Frontend. Use npm.cmd, not npm: in PowerShell, `npm` resolves to
#    npm.ps1, and a machine with the default execution policy refuses to
#    load it ("running scripts is disabled on this system"). npm.cmd is the
#    batch wrapper and is not subject to that policy.
cd frontend
npm.cmd install
npm.cmd run build
cd ..

# 4. Run
$env:LAPUS_DATABASE_URL = "Spec_Stage.db"
.venv\Scripts\python.exe -m lapus.desktop
```

For a PostgreSQL `Spec_Stage`, set instead:

```powershell
$env:LAPUS_DATABASE_URL = "postgresql://lapus_app:YOURPASSWORD@localhost:5432/Spec_Stage"
```

**macOS / Linux**

```bash
git clone https://github.com/ipalmer100/Lapus.git
cd Lapus

python3 -m venv .venv
.venv/bin/pip install -e "backend[dev]"          # add ,postgres for PostgreSQL
.venv/bin/python tools/make_demo_db.py

cd frontend && npm install && npm run build && cd ..

LAPUS_DATABASE_URL=Spec_Stage.db .venv/bin/python -m lapus.desktop
```

Either way, open http://127.0.0.1:8770/.

For frontend development with hot reload, run the two halves separately:

```bash
LAPUS_DATABASE_URL=Spec_Stage.db .venv/bin/python -m uvicorn lapus.api.app:app --port 8770 --reload
cd frontend && npm run dev      # http://localhost:5173, proxies /api
```

### Tests

```bash
.venv/bin/python -m pytest backend/tests -q     # 109 tests; 10 more with a server
cd frontend && npx tsc -b                        # typecheck

# Against a live PostgreSQL (otherwise those 10 skip):
export LAPUS_TEST_POSTGRES_URL=postgresql://lapus_app:devpassword@localhost:5432/Spec_Stage
.venv/bin/python -m pytest backend/tests -q     # 119 tests
```

## Configuration

Every value has a working default; a `.env` is optional. See `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LAPUS_DATABASE_URL` | `Spec_Stage.db`, then `Desktop/Specs/Spec_Stage.db` | The parser's staging database. A bare path means SQLite; `postgresql://` selects PostgreSQL. |
| `LAPUS_APP_DATABASE_URL` | `%APPDATA%\Lapus\lapus.db` (per-OS app data) | Where Lapus writes change requests. Never point this at the staging database. |
| `DEV_USER_EMAIL` | `developer@example.com` | Stand-in identity until real authentication. |
| `LAPUS_DEV_USER_IS_APPROVER` | `true` | Whether this user sees the approvals and admin areas. |
| `LAPUS_ALLOW_SELF_APPROVAL` | `true` | Whether one person may approve their own submission. See the security note below. |
| `BACKEND_PORT` | `8770` | |

## Database setup

**SQLite (current).** Nothing to do. Lapus creates its own `lapus.db` on first
run and attaches it as schema `lapus`. The staging database is never modified,
so it needs no migration and no permissions work.

**PostgreSQL (verified).** Apply `db/postgres/001_lapus_schema.sql` as an
administrator, create a restricted role per
[docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md), install the extra
(`pip install -e "backend[postgres]"`) and set a `postgresql://` URL. The read
boundary there is the database role rather than a connection flag, and Lapus
checks at startup that the role really lacks INSERT/UPDATE/DELETE on `public`
staging tables.

Lapus does not create the schema on a server: the application role has no DDL
rights, so an administrator applies the script and Lapus verifies it at
startup. That script is generated from `migrations.py`
(`tools/emit_schema_sql.py`) and a test fails if the two drift apart.

Run the integration suite against a real server with
`tools/make_test_postgres.py`; see LOCAL_SETUP.

**SQL Server (planned).** `backend/lapus/db/dialect.py` already describes the
differences — identity columns, `DATETIMEOFFSET`, no `IF NOT EXISTS` on
`CREATE INDEX` — and `test_dialects.py` checks the Lapus schema generates for
it. What remains is a `pyodbc` connection function alongside the other two
backends. No repository or service code changes.

## How it is put together

```text
backend/lapus/
  settings.py            resolved configuration, all defaulted
  catalog.py             the eleven sections + the identifier allowlist
  db/
    dialect.py           the SQL differences that actually bite
    engine.py            Database: SQL with `?`, rows as dicts
    sqlite_backend.py    read-only staging + attached lapus schema
    postgres_backend.py  same repositories, different connection
    migrations.py        the lapus write model, generated per dialect
  repositories/          specs.py, changes.py, admin.py — SQL lives here
  services/
    overlay.py           staged values + approved changes -> display payload
    change_workflow.py   the DRAFT -> SUBMITTED -> APPROVED state machine
    specs.py             assembling a specification workspace
  api/                   FastAPI routes, thin; also serves the built frontend
  desktop.py             the double-click launcher

frontend/src/
  components/FieldValue.tsx    every spec field renders through here
  features/spec-search/        explorer; all filtering server-side
  features/spec-workspace/     eleven sections, four layouts
  features/change-request/     propose drawer, requests, approvals
  features/admin/              parser health

config/spec_sections.json      the section contract, shared by both sides
tools/make_demo_db.py          generates a sample Spec_Stage.db
```

Two design notes worth knowing before changing anything:

**The allowlist.** All *values* reach SQL as bound parameters. But a change
item names a *table* and a *column*, and neither can be bound. Both are checked
against `config/spec_sections.json` in `catalog.py` before any SQL is built, so
nothing outside that file can reach a query as an identifier.

**Section layout is data.** Which of the four renderers a section uses — form,
table, quality matrix, timeline — comes from `spec_sections.json` through the
API, not from a switch on table names in the frontend.

## Search

Server-side, always. Free text tries customer, spec number, item, file name,
structure, structure code and path, and reaches into the bill of materials and
secondary approved materials for raw material, supplier and item code — as
`EXISTS` subqueries, so material rows are never shipped to the browser to be
filtered there. A dedicated raw-material filter answers "which specifications
use this web?" on its own.

## Security note for anything beyond the POC

Two settings are deliberately permissive so a single-user proof of concept can
demonstrate the whole workflow, and both should change before real use:

- `DEV_USER_EMAIL` is a configured identity, not an authenticated one.
  `api/deps.py::get_actor` is the single seam where real identity plugs in;
  nothing downstream trusts a request body for who is acting.
- `LAPUS_ALLOW_SELF_APPROVAL` defaults to `true`. With one configured user,
  enforcing separation of duties would make the approval queue unreachable.
  Set it to `false` the moment Lapus has more than one real user — the rule is
  implemented and tested, just not switched on.

## Further reading

- [docs/adr/0001-staging-overlay-model.md](docs/adr/0001-staging-overlay-model.md) — why approved changes are overlays
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DATABASE_CONTRACT.md](docs/DATABASE_CONTRACT.md), [docs/API_CONTRACT.md](docs/API_CONTRACT.md) — the contracts this implements
- [docs/PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md) — what it is for
- [AGENTS.md](AGENTS.md) — rules for anyone (human or agent) changing this code
- [reference/](reference/) — the parser, the corpus profiler, and prior project context
