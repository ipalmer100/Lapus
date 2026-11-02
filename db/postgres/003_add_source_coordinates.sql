-- Schema version 3: make an approved overlay survive a parser rerun.
--
-- Run once, as an administrator, against a Spec_Stage whose lapus schema was
-- created before this change. A fresh install needs only 001_lapus_schema.sql,
-- which already includes these columns.
--
-- Why: the V5.2 parser DELETEs and reinserts every row of a document on each
-- rerun, so t03_bill_of_materials.id and its siblings are regenerated. A
-- change item that targets only that surrogate id stops resolving afterwards,
-- and an approved change silently stops applying -- the record survives, its
-- effect does not. AGENTS.md rule 6 says a parser rerun must not destroy Lapus
-- changes, and until this it did.
--
-- These two columns record where the targeted row sits in the source document
-- instead. That survives a rerun, and Lapus falls back to it when the id no
-- longer resolves -- only when the staged value still matches the one captured
-- when the change was proposed, so an approved change is never re-aimed at
-- content nobody approved it against.
--
-- Idempotent: running it twice is harmless. Existing change items keep NULL
-- coordinates and continue to match by id, which is correct for any document
-- that has not been reparsed since.

BEGIN;

ALTER TABLE lapus.change_item
    ADD COLUMN IF NOT EXISTS target_source_table_index INTEGER;

ALTER TABLE lapus.change_item
    ADD COLUMN IF NOT EXISTS target_source_row INTEGER;

INSERT INTO lapus.schema_version (version)
SELECT 3
WHERE NOT EXISTS (SELECT 1 FROM lapus.schema_version WHERE version = 3);

COMMIT;
