-- Optional Lapus-friendly read views.
-- These do not modify parser-owned source data.

CREATE OR REPLACE VIEW lapus.v_spec_list AS
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
    p.structure_code,
    s.unmapped_source_tables,
    s.supplemental_source_tables,
    s.table_errors,
    s.minimum_mapping_confidence
FROM public.t00_documents d
LEFT JOIN public.t01_product_description p ON p.document_id = d.id
LEFT JOIN public.v00_document_staging_status s ON s.document_id = d.id;

CREATE INDEX IF NOT EXISTS ix_lapus_change_item_target
    ON lapus.change_item(target_document_id, target_table, target_record_id, target_field);
