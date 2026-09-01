-- Lapus application-owned schema for PostgreSQL Spec_Stage.
-- Safe boundary: this script does not alter parser-owned T00-T11 tables.

CREATE SCHEMA IF NOT EXISTS lapus;

CREATE TABLE IF NOT EXISTS lapus.change_request (
    request_id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES public.t00_documents(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'CANCELLED')),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_by TEXT,
    submitted_at TIMESTAMPTZ,
    decided_by TEXT,
    decided_at TIMESTAMPTZ,
    decision_comment TEXT
);

CREATE INDEX IF NOT EXISTS ix_lapus_change_request_document
    ON lapus.change_request(document_id);
CREATE INDEX IF NOT EXISTS ix_lapus_change_request_status
    ON lapus.change_request(status);

CREATE TABLE IF NOT EXISTS lapus.change_item (
    item_id BIGSERIAL PRIMARY KEY,
    request_id BIGINT NOT NULL REFERENCES lapus.change_request(request_id) ON DELETE CASCADE,
    target_document_id BIGINT NOT NULL REFERENCES public.t00_documents(id) ON DELETE RESTRICT,
    section_number INTEGER NOT NULL CHECK (section_number BETWEEN 1 AND 11),
    target_table TEXT NOT NULL,
    target_record_id BIGINT,
    target_field TEXT NOT NULL,
    original_value TEXT,
    proposed_value TEXT,
    change_comment TEXT,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (request_id, target_table, target_record_id, target_field)
);

CREATE INDEX IF NOT EXISTS ix_lapus_change_item_request
    ON lapus.change_item(request_id);
CREATE INDEX IF NOT EXISTS ix_lapus_change_item_document
    ON lapus.change_item(target_document_id);

CREATE TABLE IF NOT EXISTS lapus.change_event (
    event_id BIGSERIAL PRIMARY KEY,
    request_id BIGINT NOT NULL REFERENCES lapus.change_request(request_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    event_comment TEXT,
    actor TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_lapus_change_event_request
    ON lapus.change_event(request_id, created_at);

CREATE OR REPLACE VIEW lapus.v_change_request_summary AS
SELECT
    r.request_id,
    r.document_id,
    d.filename,
    p.customer,
    p.spec_number,
    p.item,
    r.title,
    r.reason,
    r.status,
    r.created_by,
    r.created_at,
    r.updated_at,
    r.submitted_by,
    r.submitted_at,
    r.decided_by,
    r.decided_at,
    r.decision_comment,
    COUNT(i.item_id) AS item_count
FROM lapus.change_request r
JOIN public.t00_documents d ON d.id = r.document_id
LEFT JOIN public.t01_product_description p ON p.document_id = r.document_id
LEFT JOIN lapus.change_item i ON i.request_id = r.request_id
GROUP BY
    r.request_id, r.document_id, d.filename, p.customer, p.spec_number, p.item,
    r.title, r.reason, r.status, r.created_by, r.created_at, r.updated_at,
    r.submitted_by, r.submitted_at, r.decided_by, r.decided_at, r.decision_comment;

CREATE OR REPLACE VIEW lapus.v_spec_change_history AS
SELECT
    r.document_id,
    r.request_id,
    r.status,
    r.title,
    i.item_id,
    i.section_number,
    i.target_table,
    i.target_record_id,
    i.target_field,
    i.original_value,
    i.proposed_value,
    i.change_comment,
    i.created_by,
    i.created_at,
    r.decided_by,
    r.decided_at
FROM lapus.change_request r
JOIN lapus.change_item i ON i.request_id = r.request_id;
