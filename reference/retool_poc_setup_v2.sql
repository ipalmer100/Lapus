-- Retool read/write proof-of-concept setup for Spec_Stage
-- Run this while connected to the Spec_Stage database in pgAdmin Query Tool.
--
-- IMPORTANT:
--   1) Change ONLY the password value below before running this script.
--   2) Do not send or store the real password in chat.
--   3) Re-running this script is safe: if retool_poc already exists, its password
--      is updated instead of trying to create the role again.
--
-- Retool receives:
--   * READ access to the parser-owned staging database objects
--   * READ/WRITE access only to t00_retool_poc_edits
--
-- T01-T11 remain parser-owned staging tables and should not be edited by Retool.


-- ============================================================================
-- 1) RETOOL LOGIN / PASSWORD
-- ============================================================================
-- EDIT THIS ONE LINE:
--
-- Example only: v_password TEXT := 'MyStrongTemporaryPassword123!';
--
DO $$
DECLARE
    v_password TEXT := 'CHANGE_ME_WITH_A_STRONG_PASSWORD';
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'retool_poc'
    ) THEN
        -- Existing login: update the password and make sure LOGIN is enabled.
        EXECUTE format(
            'ALTER ROLE retool_poc WITH LOGIN PASSWORD %L',
            v_password
        );
        RAISE NOTICE 'Updated password for existing role retool_poc.';
    ELSE
        -- First run: create the dedicated Retool login.
        EXECUTE format(
            'CREATE ROLE retool_poc LOGIN PASSWORD %L',
            v_password
        );
        RAISE NOTICE 'Created role retool_poc.';
    END IF;
END
$$;


-- ============================================================================
-- 2) DATABASE + SCHEMA READ PERMISSIONS
-- ============================================================================
GRANT CONNECT ON DATABASE "Spec_Stage" TO retool_poc;
GRANT USAGE ON SCHEMA public TO retool_poc;

-- Read all current tables in the public schema.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO retool_poc;

-- Read sequences where needed by views / generated IDs.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO retool_poc;

-- Make future parser-created tables readable by Retool.
-- NOTE: ALTER DEFAULT PRIVILEGES applies to objects created by the PostgreSQL
-- role that runs this command. Run this setup as the same database owner/login
-- that normally runs the parser if you want future objects covered automatically.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO retool_poc;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT ON SEQUENCES TO retool_poc;


-- ============================================================================
-- 3) DEDICATED RETOOL WRITE-BACK TABLE
-- ============================================================================
-- This table is intentionally separate from T01-T11 so Retool can prove
-- read/write behavior without altering the Word-derived staging values.
CREATE TABLE IF NOT EXISTS t00_retool_poc_edits (
    edit_id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL
        REFERENCES t00_documents(id)
        ON DELETE CASCADE,
    section_name TEXT NOT NULL,
    field_name TEXT NOT NULL,
    original_value TEXT,
    proposed_value TEXT,
    comments TEXT,
    edit_status TEXT NOT NULL DEFAULT 'POC',
    edited_by TEXT,
    edited_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_t00_retool_poc_edits_document_id
    ON t00_retool_poc_edits(document_id);

-- Explicit write access for the POC table only.
GRANT SELECT, INSERT, UPDATE, DELETE
ON t00_retool_poc_edits
TO retool_poc;

GRANT USAGE, SELECT
ON SEQUENCE t00_retool_poc_edits_edit_id_seq
TO retool_poc;


-- ============================================================================
-- 4) MAIN RETOOL SPEC-BROWSER VIEW
-- ============================================================================
CREATE OR REPLACE VIEW v00_retool_spec_list AS
SELECT
    d.id AS document_id,
    d.filename,
    d.relative_path,
    d.source_directory,
    d.imported_at,
    d.last_seen_at,
    d.parser_version,
    d.is_present,
    p.customer,
    p.spec_number,
    p.item,
    p.date_of_issue,
    p.structure_description,
    p.revision_number,
    p.structure_code
FROM t00_documents d
LEFT JOIN t01_product_description p
    ON p.document_id = d.id;

GRANT SELECT ON v00_retool_spec_list TO retool_poc;


-- ============================================================================
-- 5) RETOOL EDIT-HISTORY VIEW
-- ============================================================================
CREATE OR REPLACE VIEW v00_retool_edit_history AS
SELECT
    e.edit_id,
    e.document_id,
    d.filename,
    p.spec_number,
    p.item,
    e.section_name,
    e.field_name,
    e.original_value,
    e.proposed_value,
    e.comments,
    e.edit_status,
    e.edited_by,
    e.edited_at,
    e.updated_at
FROM t00_retool_poc_edits e
JOIN t00_documents d
    ON d.id = e.document_id
LEFT JOIN t01_product_description p
    ON p.document_id = e.document_id;

GRANT SELECT ON v00_retool_edit_history TO retool_poc;


-- ============================================================================
-- 6) OPTIONAL VERIFICATION QUERIES
-- ============================================================================
-- Confirm the Retool role exists:
-- SELECT rolname, rolcanlogin
-- FROM pg_roles
-- WHERE rolname = 'retool_poc';
--
-- Preview specs available to Retool:
-- SELECT *
-- FROM v00_retool_spec_list
-- WHERE is_present = 1
-- LIMIT 20;
--
-- Preview Retool write-back history:
-- SELECT *
-- FROM v00_retool_edit_history
-- ORDER BY edited_at DESC
-- LIMIT 20;


-- ============================================================================
-- PASSWORD-ONLY CHANGE FOR LATER
-- ============================================================================
-- After the initial setup, you do NOT need to rerun this whole script merely
-- to rotate the password. You can run just the following statement instead:
--
-- ALTER ROLE retool_poc
--     WITH PASSWORD 'YOUR_NEW_STRONG_PASSWORD';
--
-- Changing the PostgreSQL password does not delete the role or its permissions.
-- After changing it here, update the password in the Retool PostgreSQL resource.
