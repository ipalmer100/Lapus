# Lapus Codex Instructions

## Mission
Build Lapus as a reliable internal specification-management application over PostgreSQL `Spec_Stage`.

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
- Frontend: React + TypeScript. Vite is preferred for a simple internal app unless the repository already uses another React framework.
- Backend: FastAPI + Python.
- Database: PostgreSQL.
- Database connectivity belongs only in the backend.
- Keep a repository/service layer between API routes and SQL so the database implementation remains testable.
- Use migrations for the `lapus` schema. Do not modify parser-created tables from migrations.

## Security
- Never commit database passwords or secrets.
- Use environment variables.
- Use a dedicated database role with SELECT on `public` staging objects and read/write only on `lapus` objects.
- Do not expose raw connection errors or credentials in the browser.
- Prefer application authentication identity for `created_by`, `submitted_by`, and approval events. During local POC, a development user may be configured explicitly.

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

## Definition of done for the first MVP
- Search and select a spec.
- View all available T01-T11 sections.
- Create a draft change request against a selected field.
- Add multiple change items to one request.
- Submit the request.
- Approve/reject it in an approval view.
- See the complete change history for a spec.
- Parser-owned tables remain unchanged throughout automated tests.
