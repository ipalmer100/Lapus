-- SQLite form of the parser-owned staging schema (T00-T11).
--
-- This is NOT a migration Lapus runs. The V5.2 parser owns these objects and
-- creates them itself; this file exists so the shape is checked into the repo,
-- so tools/make_demo_db.py can build a faithful demo database, and so tests
-- have a schema to run against without the real 14,000-document corpus.
--
-- Transcribed from POSTGRES_SCHEMA_SQL in
-- reference/word_specs_to_postgres_v5_2_corpus_aware_Spec_Stage.py, with the
-- three mechanical type substitutions SQLite needs:
--   BIGSERIAL PRIMARY KEY -> INTEGER PRIMARY KEY AUTOINCREMENT
--   BIGINT                -> INTEGER
--   DOUBLE PRECISION      -> REAL
-- Column names, nullability and ordering are otherwise identical, because the
-- application queries both backends with the same SQL.

CREATE TABLE IF NOT EXISTS T00_Documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relative_path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    source_directory TEXT,
    source_file_size INTEGER,
    source_modified_ns INTEGER,
    sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    is_present INTEGER NOT NULL DEFAULT 1,
    parser_version TEXT NOT NULL,
    paragraph_content TEXT
);

CREATE TABLE IF NOT EXISTS T00_Table_Directory (
    sqlite_table_name TEXT PRIMARY KEY,
    table_number INTEGER NOT NULL,
    table_role TEXT NOT NULL,
    word_section TEXT,
    description TEXT,
    display_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS T01_Product_Description (
    document_id INTEGER PRIMARY KEY REFERENCES T00_Documents(id) ON DELETE CASCADE,
    customer TEXT,
    spec_number TEXT,
    item TEXT,
    date_of_issue TEXT,
    structure_description TEXT,
    revision_number TEXT,
    structure_code TEXT
);

CREATE TABLE IF NOT EXISTS T02_Locations (
    document_id INTEGER PRIMARY KEY REFERENCES T00_Documents(id) ON DELETE CASCADE,
    customer_location TEXT,
    facility TEXT,
    spec_originator TEXT,
    phone_number TEXT
);

CREATE TABLE IF NOT EXISTS T03_Bill_of_Materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES T00_Documents(id) ON DELETE CASCADE,
    source_table_index INTEGER,
    source_row INTEGER NOT NULL,
    row_type TEXT NOT NULL,
    basis_weight TEXT,
    basis_weight_range TEXT,
    caliper_mils TEXT,
    raw_material TEXT,
    supplier TEXT,
    raw_material_item_code TEXT
);

CREATE TABLE IF NOT EXISTS T04_Secondary_Approved_Materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES T00_Documents(id) ON DELETE CASCADE,
    source_table_index INTEGER,
    source_row INTEGER NOT NULL,
    row_type TEXT NOT NULL,
    basis_weight TEXT,
    basis_weight_range TEXT,
    caliper_mils TEXT,
    raw_material TEXT,
    supplier TEXT,
    raw_material_item_code TEXT
);

CREATE TABLE IF NOT EXISTS T05_Process_Routing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES T00_Documents(id) ON DELETE CASCADE,
    source_table_index INTEGER,
    source_row INTEGER NOT NULL,
    pass TEXT,
    process TEXT,
    machine TEXT,
    process_conditions TEXT,
    comments TEXT
);

CREATE TABLE IF NOT EXISTS T06_Physical_Attributes_Testing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES T00_Documents(id) ON DELETE CASCADE,
    source_table_index INTEGER,
    source_row INTEGER NOT NULL,
    pass_name TEXT,
    attribute TEXT,
    coa TEXT,
    units TEXT,
    lsl TEXT,
    lcl TEXT,
    target TEXT,
    ucl TEXT,
    usl TEXT,
    procedure TEXT,
    frequency TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS T07_Slitting_Information (
    document_id INTEGER PRIMARY KEY REFERENCES T00_Documents(id) ON DELETE CASCADE,
    slit_width TEXT,
    core_id TEXT,
    splice_tape TEXT,
    width_tolerance TEXT,
    core_type TEXT,
    splice_type TEXT,
    cutoff TEXT,
    lineal_ft_per_roll TEXT,
    splice_location TEXT,
    eyemark_location TEXT,
    maximum_od TEXT,
    splice_stamp_flag TEXT,
    number_of_cuts TEXT,
    maximum_weight TEXT,
    maximum_splices TEXT,
    unwind TEXT,
    labels_across TEXT,
    core_tags TEXT,
    splice_code TEXT,
    splicing TEXT,
    end_of_roll_indicator TEXT,
    comments TEXT
);

CREATE TABLE IF NOT EXISTS T08_Packing_Information (
    document_id INTEGER PRIMARY KEY REFERENCES T00_Documents(id) ON DELETE CASCADE,
    pallet_size TEXT,
    poly_bags TEXT,
    pallet_labels TEXT,
    pallet_type TEXT,
    core_plugs TEXT,
    protective_corners TEXT,
    rolls_per_layer TEXT,
    roll_cradles TEXT,
    stretch_wrap_pallet TEXT,
    layers_per_pallet TEXT,
    tier_dividers TEXT,
    band_pallet TEXT,
    rolls_per_pallet TEXT,
    top_layer TEXT,
    wooden_top TEXT,
    feet_per_pallet TEXT,
    end_boards TEXT,
    packing_instructions TEXT,
    additional_instructions TEXT
);

CREATE TABLE IF NOT EXISTS T09_Reporting_Requirements (
    document_id INTEGER PRIMARY KEY REFERENCES T00_Documents(id) ON DELETE CASCADE,
    coa_required TEXT,
    coa_recipients TEXT,
    coa_format TEXT,
    coa_frequency TEXT,
    values_to_report_on_coa TEXT
);

CREATE TABLE IF NOT EXISTS T10_Customer_Sampling_Requirements (
    document_id INTEGER PRIMARY KEY REFERENCES T00_Documents(id) ON DELETE CASCADE,
    samples_required TEXT,
    send_to TEXT,
    number_of_samples TEXT,
    sample_preparation_labeling TEXT
);

CREATE TABLE IF NOT EXISTS T11_Revision_History (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES T00_Documents(id) ON DELETE CASCADE,
    source_table_index INTEGER,
    source_row INTEGER NOT NULL,
    revision_number TEXT,
    who TEXT,
    revision_date TEXT,
    revision TEXT
);

CREATE TABLE IF NOT EXISTS T00_Ingestion_Audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER REFERENCES T00_Documents(id) ON DELETE CASCADE,
    relative_path TEXT,
    filename TEXT NOT NULL,
    source_table_index INTEGER,
    detected_section TEXT,
    row_count INTEGER,
    column_count INTEGER,
    status TEXT NOT NULL,
    mapping_method TEXT,
    mapping_confidence REAL,
    details TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS T00_Unmapped_Tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES T00_Documents(id) ON DELETE CASCADE,
    source_table_index INTEGER,
    preceding_heading TEXT,
    signature TEXT,
    classification TEXT,
    suggested_section TEXT,
    mapping_method TEXT,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS T00_Ingestion_Errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relative_path TEXT,
    filename TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_documents_filename ON T00_Documents(filename);
CREATE INDEX IF NOT EXISTS ix_documents_present ON T00_Documents(is_present);
CREATE INDEX IF NOT EXISTS ix_bom_document ON T03_Bill_of_Materials(document_id);
CREATE INDEX IF NOT EXISTS ix_secondary_document ON T04_Secondary_Approved_Materials(document_id);
CREATE INDEX IF NOT EXISTS ix_routing_document ON T05_Process_Routing(document_id);
CREATE INDEX IF NOT EXISTS ix_testing_document ON T06_Physical_Attributes_Testing(document_id);
CREATE INDEX IF NOT EXISTS ix_revision_document ON T11_Revision_History(document_id);

-- Parser QA views. CREATE OR REPLACE is PostgreSQL-only; SQLite needs the
-- IF NOT EXISTS form.
CREATE VIEW IF NOT EXISTS V00_Document_Staging_Status AS
SELECT
    d.id AS document_id,
    d.relative_path,
    d.filename,
    d.parser_version,
    d.is_present,
    SUM(CASE WHEN a.status = 'mapped' THEN 1 ELSE 0 END) AS mapped_source_tables,
    SUM(CASE WHEN a.status = 'supplemental' THEN 1 ELSE 0 END) AS supplemental_source_tables,
    SUM(CASE WHEN a.status = 'unmapped' THEN 1 ELSE 0 END) AS unmapped_source_tables,
    SUM(CASE WHEN a.status = 'error' THEN 1 ELSE 0 END) AS table_errors,
    MIN(CASE WHEN a.mapping_confidence IS NULL THEN 1.0 ELSE a.mapping_confidence END)
        AS minimum_mapping_confidence
FROM T00_Documents d
LEFT JOIN T00_Ingestion_Audit a ON a.document_id = d.id
GROUP BY d.id, d.relative_path, d.filename, d.parser_version, d.is_present;

CREATE VIEW IF NOT EXISTS V00_Exception_Worklist AS
SELECT
    d.relative_path,
    a.source_table_index,
    a.detected_section,
    a.status,
    a.mapping_method,
    a.mapping_confidence,
    a.details
FROM T00_Ingestion_Audit a
JOIN T00_Documents d ON d.id = a.document_id
WHERE a.status <> 'mapped'
ORDER BY d.relative_path, a.source_table_index;
