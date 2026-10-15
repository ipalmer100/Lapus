-- Lapus application-owned schema for PostgreSQL.
--
-- GENERATED FILE -- do not edit by hand.
-- Regenerate with:  python tools/emit_schema_sql.py --dialect postgres
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


CREATE SCHEMA IF NOT EXISTS lapus;

CREATE TABLE IF NOT EXISTS lapus.schema_version (
    version INTEGER NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lapus.change_request (
    request_id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED','CANCELLED')),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_by TEXT,
    submitted_at TIMESTAMPTZ,
    decided_by TEXT,
    decided_at TIMESTAMPTZ,
    decision_comment TEXT
);

CREATE TABLE IF NOT EXISTS lapus.change_item (
    item_id BIGSERIAL PRIMARY KEY,
    request_id BIGINT NOT NULL
        REFERENCES lapus.change_request(request_id) ON DELETE CASCADE,
    target_document_id BIGINT NOT NULL,
    section_number INTEGER NOT NULL CHECK (section_number BETWEEN 1 AND 11),
    target_table TEXT NOT NULL,
    target_record_id BIGINT,
    target_field TEXT NOT NULL,
    original_value TEXT,
    proposed_value TEXT,
    -- Distinguishes "propose an empty value" from "no value proposed",
    -- which a nullable proposed_value alone cannot express. See
    -- PRODUCT_REQUIREMENTS.md: an intentional clear must be explicit.
    clears_value INTEGER NOT NULL DEFAULT 0,
    change_comment TEXT,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lapus.change_event (
    event_id BIGSERIAL PRIMARY KEY,
    request_id BIGINT NOT NULL
        REFERENCES lapus.change_request(request_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    event_comment TEXT,
    actor TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_lapus_change_request_document ON lapus.change_request(document_id);

CREATE INDEX IF NOT EXISTS ix_lapus_change_request_status ON lapus.change_request(status);

CREATE INDEX IF NOT EXISTS ix_lapus_change_item_request ON lapus.change_item(request_id);

CREATE INDEX IF NOT EXISTS ix_lapus_change_item_target ON lapus.change_item(target_document_id, target_table, target_record_id, target_field);

CREATE INDEX IF NOT EXISTS ix_lapus_change_event_request ON lapus.change_event(request_id, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS ux_lapus_change_item_row_target ON lapus.change_item(request_id, target_table, target_record_id, target_field) WHERE target_record_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_lapus_change_item_doc_target ON lapus.change_item(request_id, target_table, target_field) WHERE target_record_id IS NULL;

-- Record the schema version the application expects.
INSERT INTO lapus.schema_version (version)
SELECT 1
WHERE NOT EXISTS (SELECT 1 FROM lapus.schema_version);
