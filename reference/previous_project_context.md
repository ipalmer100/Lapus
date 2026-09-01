# Spec Modernization Project Context

## Purpose

This repository/folder is a proof-of-concept and eventual production application for modernizing manufacturing product specifications that currently live in Microsoft Word documents.

The source population is approximately **14,000 active Word specification documents**, stored recursively beneath a Windows Desktop folder named:

```text
Desktop\Specs
```

The project converts those documents into structured database records so manufacturing, quality, supply chain, engineering, and other users can search and consume specification data without manually opening Word files.

The current working database technology is **SQLite**. The intended future production database is **SQL Server**, so frontend/database code should be designed so the data-access layer can be swapped later without rewriting the UI.

---

## Current Source-of-Truth Files

Codex should inspect these files before making architectural changes:

```text
word_specs_to_sqlite_v5_corpus_aware_Spec_Stage.py
spec_corpus_profiler_sqlite.py
Spec_Stage.db
```

The parser and profiler evolved through several iterations. The V5 parser is the current staging implementation and should be treated as the active baseline.

---

## Current Database

Default SQLite database:

```text
Spec_Stage.db
```

Default location when running the lift script:

```text
Desktop\Specs\Spec_Stage.db
```

The application should treat the database as **read-only by default** unless an explicit future requirement introduces controlled editing.

---

## Database Naming Convention

The database is intentionally ordered to mirror the Word specification structure.

### Control / QA tables

All control, audit, ingestion, and exception tables are numbered `T00`.

Typical examples include:

```text
T00_Documents
T00_Table_Directory
T00_Ingestion_Audit
T00_Unmapped_Tables
T00_Ingestion_Errors
```

The V5 parser may add additional T00 metadata or QA objects. Codex should inspect the live SQLite schema instead of assuming the above list is exhaustive.

### Specification staging tables

```text
T01_Product_Description
T02_Locations
T03_Bill_of_Materials
T04_Secondary_Approved_Materials
T05_Process_Routing
T06_Physical_Attributes_Testing
T07_Slitting_Information
T08_Packing_Information
T09_Reporting_Requirements
T10_Customer_Sampling_Requirements
T11_Revision_History
```

`T01` through `T11` represent the logical business sections of a manufacturing specification.

Do **not** assume that every historical Word document physically contains exactly 11 Word tables. The parser maps variable legacy structures into these 11 logical sections.

---

## Relational Model

`T00_Documents` is the parent/source-document table.

The principal relational key is:

```text
document_id
```

Child staging records in T01-T11 are associated back to the source document using `document_id`.

The V4/V5 generation also introduced source traceability using the relative document path beneath `Desktop\Specs` so duplicate filenames in different subfolders do not collide.

Important source-document metadata may include fields such as:

```text
relative_path
filename
source_directory
source_file_size
source_modified_ns
sha256
imported_at
last_seen_at
is_present
parser_version
```

Codex should inspect the actual SQLite schema for exact names and types before writing queries.

---

## Current Ingestion Behavior

The lift script recursively scans every `.docx` file beneath:

```text
Desktop\Specs
```

Key behaviors already implemented include:

- recursive subfolder scanning
- incremental ingestion
- changed-file detection
- parser-version awareness
- relative-path identity instead of filename-only identity
- handling duplicate filenames safely
- retaining missing documents in metadata rather than immediately deleting their staged data
- optional pruning of missing files
- backups before major schema/parser migrations
- preservation of unmapped/supplemental tables rather than silently discarding them
- ingestion audit and error logging

The frontend should **not** duplicate this ingestion logic. Treat the database as the output of the parser.

---

## Corpus Profiling Work

A separate profiler was created to analyze the real Word-document population before expanding parser rules:

```text
spec_corpus_profiler_sqlite.py
```

It recursively profiles the Word corpus and creates a separate structural-analysis database and CSV/ZIP outputs beneath:

```text
Desktop\Specs\_Corpus_Profile
```

The profiler was designed to identify:

- document layout families
- Word/XML layout variants
- table signatures
- heading variants
- section coverage
- unmapped tables
- structural exceptions

A real corpus profile supplied during development represented **1,811 successfully profiled specifications**. The V5 parser was upgraded based on the observed variation in that corpus.

---

## V5 Parser Capabilities

The V5 parser is **corpus-aware** rather than position-only.

It should be treated as supporting, among other things:

- legacy heading variations
- typo-tolerant heading recognition
- punctuation variations
- bilingual section headings
- content-based table recovery when headings are damaged or missing
- dynamic column mapping for tables whose column counts changed historically
- split Physical Attributes & Testing tables
- supplemental/comment tables associated with a main section
- multiple Packing Information tables
- Word merged-cell irregularities
- flexible Product Description header layouts
- source-table traceability
- mapping method / confidence metadata in ingestion audit data
- classification of truly supplemental manufacturing tables into T00 rather than incorrectly forcing them into T01-T11

Examples of observed historical heading variation included forms similar to:

```text
eLocations
Bill of Materials-
Physical Attribues & Testing
9Revision History
litting Information
```

Bilingual variants were also observed for sections such as Process Routing, Secondary Approved Materials, and Packing Information.

The frontend should not expose these parser complexities to ordinary users, but an administrator/QA view should make them discoverable.

---

## Frontend Goal

Build a frontend that proves Word-based specifications can be consumed as structured, queryable manufacturing data.

The initial frontend should be **read-only** and optimized for business/manufacturing users rather than database developers.

### Primary user experience

Users should be able to:

1. Search specifications.
2. Open one specification.
3. Read its T01-T11 sections in a clear order matching the source specification.
4. Search/filter BOM and secondary-approved-material data.
5. See source-document traceability.
6. Understand whether a specification staged successfully.
7. Access ingestion/parser exceptions when appropriate without cluttering the normal specification view.

---

## Search Requirements

At minimum, design search around the data actually present in the database, including likely use cases such as:

- spec number
- finished-good / item / part number
- filename
- customer
- raw material
- raw-material item code
- supplier

Do not hard-code column names until the live schema has been inspected.

Search should be fast and forgiving enough for users who only know part of an identifier or description.

---

## Specification Detail Page

A specification detail page should present the logical document sections in this order:

```text
01 Product Description
02 Locations
03 Bill of Materials
04 Secondary Approved Materials
05 Process Routing
06 Physical Attributes & Testing
07 Slitting Information
08 Packing Information
09 Reporting Requirements
10 Customer Sampling Requirements
11 Revision History
```

The page should tolerate missing sections gracefully.

Suggested UX pattern:

- persistent specification header / identity block
- left-side section navigation or compact tabs
- readable card/table presentation by section
- direct links or anchors to major tables
- clear source filename and relative source path
- parser/staging status shown subtly for normal users

Do not expose raw database table names as the primary labels in the business-facing UI.

---

## Important Table Presentation Rules

### Bill of Materials

`T03_Bill_of_Materials` is a major user-facing table.

Prioritize fields representing concepts such as:

- basis weight
- basis-weight range / tolerance
- caliper
- raw material description
- supplier
- raw-material item code

Use the actual schema rather than assuming exact field names.

### Secondary Approved Materials

`T04_Secondary_Approved_Materials` should look and behave similarly to BOM but must remain visually distinct because these are alternate/approved materials rather than the primary BOM.

### Process Routing

`T05_Process_Routing` should make pass sequence, process, machine, conditions, and comments easy to scan.

### Physical Attributes & Testing

`T06_Physical_Attributes_Testing` may contain fields conceptually similar to:

- pass
- attribute
- COA indicator
- units
- LSL
- LCL
- target
- UCL
- USL
- procedure
- frequency
- notes/comments

The exact schema can vary because the parser normalizes multiple historical Word layouts.

### Revision History

`T11_Revision_History` should be chronological and easy to scan. It can be long, so consider a compact timeline/table treatment.

---

## Administrator / QA Experience

Normal manufacturing users should not have to interpret parser internals.

Provide a separate administrator or data-quality area based on T00 tables/views.

Useful information includes:

- staged document count
- successfully mapped tables
- supplemental tables
- unmapped tables
- ingestion errors
- mapping confidence
- parser version
- changed/missing source documents

If present in the database, useful QA views may include names similar to:

```text
V00_Document_Staging_Status
V00_Exception_Worklist
```

Inspect the database before relying on those names.

---

## Architecture Requirements

### 1. Keep database access isolated

Do not scatter raw SQLite queries throughout UI components.

Use a repository/data-access layer such as:

```text
UI
  -> service layer
      -> repository / data-access interface
          -> SQLite implementation now
          -> SQL Server implementation later
```

This requirement is important because the project is expected to migrate to SQL Server when IT resources are available.

### 2. Read-only first

Do not add specification editing, deletion, or staging mutation to the frontend unless explicitly requested.

### 3. Do not rewrite the parser casually

The V5 parser encodes corpus-derived handling for real legacy Word-document variation. Frontend work should not modify parser behavior unless the task explicitly involves ingestion.

### 4. Handle missing/legacy data gracefully

Older specifications may lack one or more logical sections or fields.

The UI must not fail because a field or child record is absent.

### 5. Avoid assuming all source tables are identical

The staging schema is more stable than the original Word structure. Use the staged logical tables rather than trying to infer Word-table position from the frontend.

### 6. Preserve source traceability

Where useful, show:

```text
source filename
relative source path
document_id
parser version
last staged/imported timestamp
```

`document_id` may be hidden from normal business users but should remain accessible for support/debugging.

---

## Suggested Technology Direction

Codex should inspect the environment/repository before selecting a stack.

For a local proof of concept, a lightweight architecture is preferred over an unnecessarily complex enterprise stack.

Reasonable options include:

- Python backend with FastAPI or Flask plus a modern lightweight frontend
- a local web application with a clear repository layer
- another maintainable stack if it materially improves deployment or usability

The key constraint is **easy future migration from SQLite to SQL Server**, not a specific framework.

Before implementation, Codex should propose the architecture and explain why it fits this requirement.

---

## Recommended First Codex Task

Start by inspecting:

```text
Spec_Stage.db
word_specs_to_sqlite_v5_corpus_aware_Spec_Stage.py
spec_corpus_profiler_sqlite.py
```

Then:

1. inventory the SQLite schema, tables, views, keys, and indexes;
2. identify the most useful searchable columns;
3. propose a frontend/backend architecture;
4. design a read-only specification browser;
5. implement the smallest functional vertical slice:
   - specification search
   - result list
   - specification detail page
   - T03 BOM display
   - T04 Secondary Approved Materials display
   - source-document metadata
   - basic staging status;
6. keep database access behind an abstraction suitable for SQL Server later;
7. add automated tests around repository queries and specification-detail assembly.

Do not implement broad editing/workflow functionality in the first pass.

---

## Suggested Product Language

Use manufacturing/business language in the UI.

Prefer:

```text
Product Description
Bill of Materials
Secondary Approved Materials
Process Routing
Physical Attributes & Testing
Slitting Information
Packing Information
Reporting Requirements
Revision History
```

Avoid showing labels like `T03_Bill_of_Materials` unless the user is in an admin/debug view.

---

## Project Direction

The long-term concept is:

```text
Word Specifications
        |
        v
Corpus Profiling / Structural Classification
        |
        v
V5+ Word Parser
        |
        v
Spec_Stage
        |
        +--> Manufacturing Specification Frontend
        |
        +--> QA / Exception Management
        |
        +--> Future ERP / Radius alignment
        |
        v
Future SQL Server Production Architecture
```

The goal is not merely to display Word text on a webpage. The value proposition is that specification content is now **structured data** that can be searched, validated, compared, governed, and eventually aligned with ERP master data.

---

## Guardrails for Codex

- Inspect the actual DB schema before coding against it.
- Do not assume every spec has every section.
- Do not assume every table has rows.
- Do not modify `Spec_Stage.db` during normal frontend use.
- Do not discard T00 exception/audit information.
- Do not couple UI code directly to SQLite-specific syntax when avoidable.
- Preserve `document_id` relationships.
- Preserve relative-path source identity.
- Prefer maintainable, explicit code over clever abstractions.
- Keep the first frontend iteration simple enough to demo reliably.
- Build for future SQL Server migration, but do not introduce SQL Server dependencies yet.

