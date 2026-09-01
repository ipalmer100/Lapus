# Lapus - instructions for anyone changing this code

## Mission
A reliable internal specification-management application over the `Spec_Stage`
staging database the V5.2 Word parser produces.

## Current state
The MVP described below is **built**. Read `README.md` for how it fits
together and `docs/adr/0001-staging-overlay-model.md` for the decision the
whole design rests on before changing anything structural.

The database is **SQLite** today, with PostgreSQL scaffolded and SQL Server
planned. Where the rules below say PostgreSQL, they mean whichever backend is
configured -- the `lapus` schema exists on all three (via ATTACH on SQLite),
and repository code is written once against `db/engine.py`.

## Non-negotiable data rules
1. Treat `public.t01_*` through `public.t11_*` as parser-owned, read-only staging data.
2. Never UPDATE, INSERT, or DELETE T01-T11 from application code unless the user explicitly changes the architecture.
3. Application writes belong in the `lapus` schema.
4. Preserve `document_id` as the parent key across the application.
5. Preserve row targeting for repeating tables using the source table primary key (`id`) whenever available.
6. A parser rerun must not destroy Lapus changes.
7. Do not invent missing spec values. Missing source sections are valid states.
8. Keep source-document revision history (`t11_revision_history`) distinct from Lapus workflow/change history.
9. Supplemental/unmapped parser content belongs to T00 diagnostics; do not silently force it into T01-T11.
10. Build all database writes with parameterized queries/ORM bindings. Never concatenate user input into SQL.

## UX rules
- Use manufacturing/business terminology, not raw table names, in the normal UI.
- Desktop-first, responsive second.
- Specification reading is the primary experience; diagnostics are secondary/admin-only.
- Make current staged values visually distinct from proposed/approved Lapus changes.
- Never silently replace an original value. Show provenance.
- Empty sections should say that no information is available, not error.
- Repeating sections: BOM, secondary materials, routing, physical testing, revision history.
- Single-record sections: product description, locations, slitting, packing, reporting, sampling.

## Architecture
- Frontend: React + TypeScript on Vite. No router: navigation is four views
  and state lives in `App.tsx`.
- Backend: FastAPI + Python, which also serves the built frontend so the
  packaged executable is one process on one port.
- Database: SQLite now, SQL Server intended. Never write backend-specific SQL
  in a repository -- put the difference in `db/dialect.py`, which is where the
  three backends' divergences (placeholders, index/FK qualification, identity
  columns, `IF NOT EXISTS` support) are already described.
- Database connectivity belongs only in the backend.
- Keep the repository/service layer between API routes and SQL.
- Use `db/migrations.py` for the `lapus` schema. It generates per dialect;
  do not hand-maintain parallel scripts. Migrations must never reference a
  T00-T11 object -- a foreign key to `t00_documents` would make a parser rerun
  fail or cascade application data away. `test_dialects.py` enforces this.
- Table and column names cannot be bound as parameters. Every one that reaches
  SQL must first pass `catalog.validate_target`, which checks it against
  `config/spec_sections.json`. Do not bypass this.

## Security
- Never commit database passwords or secrets.
- Use environment variables.
- Use a dedicated database role with SELECT on `public` staging objects and read/write only on `lapus` objects.
- Do not expose raw connection errors or credentials in the browser.
- Prefer application authentication identity for `created_by`, `submitted_by`, and approval events. During local POC, a development user may be configured explicitly.
- `api/deps.py::get_actor` is the single seam where real identity plugs in.
  Nothing downstream may take who-is-acting from a request body.
- `LAPUS_ALLOW_SELF_APPROVAL` defaults to true so the single-user POC can
  demonstrate approvals at all. Separation of duties is implemented and tested;
  turn it on as soon as there is more than one real user.

## Change workflow
Initial supported statuses:
- DRAFT
- SUBMITTED
- APPROVED
- REJECTED
- CANCELLED

Only DRAFT change requests are editable by their creator in the MVP.
Submission freezes change items until approved/rejected.
All status transitions create `lapus.change_event` records.

## Packaging
The app ships as a PyInstaller folder containing `Lapus.exe`. See
`packaging/README.md`. If you add a Python dependency that is imported
dynamically, add it to `hiddenimports` in `packaging/lapus.spec`; if you add a
data file the app reads at runtime, add it to `datas` there and load it via
`sys._MEIPASS` when frozen (see `catalog._config_path`).

## Definition of done for the first MVP
- Search and select a spec.
- View all available T01-T11 sections.
- Create a draft change request against a selected field.
- Add multiple change items to one request.
- Submit the request.
- Approve/reject it in an approval view.
- See the complete change history for a spec.
- Parser-owned tables remain unchanged throughout automated tests.
