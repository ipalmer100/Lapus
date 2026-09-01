# PostgreSQL Database Contract

Database: `Spec_Stage`

PostgreSQL folds the parser's unquoted logical T00-T11 identifiers to lowercase.

## Parser-owned public schema

### public.t00_documents
Parent record for a source Word document.
Key fields:
- `id` bigint primary key
- `relative_path` unique
- `filename`
- `source_directory`
- `source_file_size`
- `source_modified_ns`
- `sha256`
- `imported_at`
- `last_seen_at`
- `is_present`
- `parser_version`
- `paragraph_content`

### public.t01_product_description
Primary key: `document_id`
Fields:
- customer
- spec_number
- item
- date_of_issue
- structure_description
- revision_number
- structure_code

### public.t02_locations
Primary key: `document_id`
Fields:
- customer_location
- facility
- spec_originator
- phone_number

### public.t03_bill_of_materials
Primary key: `id`
Foreign key: `document_id`
Fields:
- source_table_index
- source_row
- row_type
- basis_weight
- basis_weight_range
- caliper_mils
- raw_material
- supplier
- raw_material_item_code

### public.t04_secondary_approved_materials
Same repeating material structure as T03.

### public.t05_process_routing
Primary key: `id`
Foreign key: `document_id`
Fields:
- source_table_index
- source_row
- pass
- process
- machine
- process_conditions
- comments

### public.t06_physical_attributes_testing
Primary key: `id`
Foreign key: `document_id`
Fields:
- source_table_index
- source_row
- pass_name
- attribute
- coa
- units
- lsl
- lcl
- target
- ucl
- usl
- procedure
- frequency
- notes

### public.t07_slitting_information
Primary key: `document_id`
Includes slit width, core, splice, cutoff, roll length, unwind, labels, and comments fields.

### public.t08_packing_information
Primary key: `document_id`
Includes pallet, rolls/layer, layers/pallet, wrapping, labels, dividers, feet/pallet, and instruction fields.

### public.t09_reporting_requirements
Primary key: `document_id`
Fields:
- coa_required
- coa_recipients
- coa_format
- coa_frequency
- values_to_report_on_coa

### public.t10_customer_sampling_requirements
Primary key: `document_id`
Fields:
- samples_required
- send_to
- number_of_samples
- sample_preparation_labeling

### public.t11_revision_history
Primary key: `id`
Foreign key: `document_id`
Fields:
- source_table_index
- source_row
- revision_number
- who
- revision_date
- revision

## Parser diagnostics
Important objects include:
- `public.t00_ingestion_audit`
- `public.t00_unmapped_tables`
- `public.t00_ingestion_errors`
- `public.v00_document_staging_status`
- `public.v00_exception_worklist`

These should be admin-only in the UI.

## Lapus-owned schema
Created by `db/001_lapus_schema.sql`.

### lapus.change_request
One workflow container for one specification.

### lapus.change_item
One proposed field-level modification. A request can contain multiple items.

Target identity is deliberately generic:
- `target_table`
- `target_record_id` for repeating source tables
- `target_document_id` for one-row-per-document source tables
- `target_field`

### lapus.change_event
Append-only workflow/audit events.

## Read/write boundary
Application database role should have:
- SELECT on parser-owned `public` staging tables/views.
- SELECT/INSERT/UPDATE as required on `lapus` tables.
- NO UPDATE/DELETE/INSERT on `public.t01_*` through `public.t11_*`.
