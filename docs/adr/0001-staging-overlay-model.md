# ADR 0001: Approved changes are overlays, not edits

Status: accepted
Date: 2026-09-01

## Context

Specification content reaches Lapus through a pipeline it does not own:

```text
~14,000 Word specifications -> V5.2 corpus-aware parser -> Spec_Stage (T00-T11) -> Lapus
```

The parser is not a one-time import. It runs again whenever documents change,
and when it does it deletes and reinserts the staged rows for each document it
re-reads. `document_id` values and repeating-row `id` values are assigned by
that process.

Users need to correct specification data — a supplier that has been
requalified, a control limit that moved, a pallet pattern that is wrong. The
obvious implementation is to let an approved change write back into
`t03_bill_of_materials` and be done.

That implementation loses on two counts:

1. **The next parser run destroys it.** The row carrying the edit is deleted
   and replaced from the Word document, which still says the old thing. The
   change disappears with no trace and no warning.
2. **It destroys provenance.** Once the staged value has been overwritten,
   nothing records what the source document actually said. The staging layer
   stops being an accurate representation of the Word corpus, which is the one
   job it exists to do — and the organisation's stated direction is to use it
   to compare, validate and govern specifications against ERP master data.

## Decision

Lapus never writes to `t01_*` through `t11_*`. Approved changes are stored in
an application-owned `lapus` schema and **rendered over** the staged values at
read time.

Three parts:

**Separate write model.** `lapus.change_request`, `lapus.change_item` and
`lapus.change_event` hold workflow and proposals. A change item names its
target generically — `target_table`, `target_record_id` (or
`target_document_id` for single-record sections), `target_field` — so the
model does not need a column per section.

**Enforcement at the connection, not in code.** On SQLite the staging database
is opened `mode=ro` and the Lapus store is ATTACHed as schema `lapus`. SQLite
applies open flags per attached database, so a write to a staging table fails
inside the engine. The boundary is a property of the connection; no
application bug can cross it. On PostgreSQL and SQL Server the same boundary is
a database role with SELECT on `public` and read/write on `lapus`, checked at
startup.

**Both values shown, always.** Every specification field is returned as a
record — `value`, `source_value`, `is_overridden`, `provenance` — never as a
bare string. The UI renders the effective value prominently with the
Word-source value beside it and the approving decision one click away. A
consumer cannot lose the distinction by accident, because there is no plain
value to read.

## Consequences

**What this buys.**

A parser rerun cannot destroy user work: it rewrites `public`, and Lapus data
lives in `lapus` (in a separate file entirely, under SQLite). Provenance is
permanent — for any field, the source value, the proposal, its author, its
approver and its reason are all still there. And the staging layer stays a
faithful representation of the Word corpus, so it can still be used to
reconcile against ERP data.

**What it costs.**

Reads carry an overlay join, and a "current value" is a computed thing rather
than a column — every consumer of specification data has to go through the
API rather than querying `t03_bill_of_materials` directly and expecting the
truth. Approved changes accumulate indefinitely; nothing prunes them. Two
approved requests may target the same field, and the rule that the later
decision wins is a convention this codebase enforces at read time rather than
something the schema prevents.

The largest cost is that an approved change does not reach the Word document.
The source specification still says the old thing, and Lapus is explicit about
that in the UI rather than hiding it. Closing that loop — writing back to the
`.docx`, or generating documents from governed data — is the point at which
the organisation would decide the database is the system of record. This ADR
deliberately does not assume that decision has been made.

## Alternatives considered

**Write into T01-T11 and re-apply after each parser run.** Requires the parser
to know about Lapus and re-apply changes after every rerun; a mismatch between
a change and a document that has since moved on silently reintroduces stale
data. Rejected: it makes the parser responsible for application semantics.

**Copy staged rows into a Lapus-owned table on first edit.** A "checked out"
copy diverges from the source with no continuing relationship to it, and gives
two competing versions with no rule for reconciling them.

**Version the staging tables themselves.** Effective, and the right answer if
the database becomes the system of record. Rejected for now because it changes
parser-owned schema, which this project explicitly does not do.
