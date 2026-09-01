# Project Context

## Problem
Manufacturing specifications currently exist as Word documents. The extraction pipeline converts their relatively consistent tables into structured PostgreSQL staging data so the organization can search, compare, govern, and eventually manage specifications as data rather than as documents.

## Corpus work completed
A corpus profiler was built to study structural variation across active Word specs, including nested folders. The parser was upgraded based on observed heading variants, bilingual headings, merged-cell differences, legacy layouts, supplemental tables, and content signatures.

The current production-style parser is V5.2 and targets PostgreSQL database `Spec_Stage`.

## Parser philosophy
- Preserve provenance.
- Detect by heading and table content, not table position alone.
- Tolerate missing sections and legacy formats.
- Preserve supplemental/unmapped content losslessly in T00 controls.
- Make parser results queryable rather than flattening a Word document into a text blob.

## Current relational model
T00 objects are control/QA metadata.
T01-T11 correspond to the standardized specification sections in document order.

The application should build on this staging layer, not replace it.

## Why Lapus has its own schema
A parser refresh can delete/reinsert staging rows. If application edits were written directly into parser-owned tables, those edits could disappear or corrupt provenance.

Lapus therefore uses a separate PostgreSQL schema for user changes and workflow. The UI can present approved values as overlays without modifying the Word-derived source rows.

## Future direction
After the POC is proven, the organization may choose to make a governed database master the system of record and generate documents from structured data. Lapus should not assume that transition has already happened.
