// Shapes returned by the Lapus API. Kept in one file so a backend change that
// alters a payload surfaces as a type error at every use site.

/** A field, with its staged origin and any approved change laid over it.
 *
 * The backend never sends a bare value for spec content: `value` is what to
 * show, `sourceValue` is what the Word document said, and both stay visible.
 * See docs/adr/0001-staging-overlay-model.md. */
export interface FieldValue {
  value: string | null
  source_value: string | null
  is_overridden: boolean
  provenance: Provenance | null
}

export interface Provenance {
  request_id: number
  request_title: string
  item_id: number
  changed_by: string
  changed_at: string
  approved_by: string | null
  approved_at: string | null
  comment: string | null
  original_value: string | null
  cleared: boolean
}

export interface SpecSummary {
  document_id: number
  filename: string
  relative_path: string
  source_directory: string | null
  imported_at: string
  last_seen_at: string
  parser_version: string
  is_present: number
  customer: string | null
  spec_number: string | null
  item: string | null
  date_of_issue: string | null
  structure_description: string | null
  revision_number: string | null
  structure_code: string | null
}

export interface SearchResponse {
  results: SpecSummary[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface StagingStatus {
  document_id: number
  relative_path: string
  filename: string
  parser_version: string
  is_present: number
  mapped_source_tables: number
  supplemental_source_tables: number
  unmapped_source_tables: number
  table_errors: number
  minimum_mapping_confidence: number
}

export interface SectionSummary {
  number: number
  key: string
  label: string
  layout: string
  is_editable: boolean
  row_count: number
  is_empty: boolean
  override_count: number
}

export interface SpecDetail {
  document_id: number
  header: SpecSummary
  staging_status: StagingStatus | null
  sections: SectionSummary[]
  approved_override_count: number
  supplemental_table_count: number
}

export interface SectionRow {
  record_id: number | null
  identity: Record<string, string | number | null>
  fields: Record<string, FieldValue>
  has_overrides: boolean
}

export interface Section {
  number: number
  key: string
  label: string
  layout: string
  table: string
  primary_key: string
  is_repeating: boolean
  is_editable: boolean
  editable_fields: string[]
  rows: SectionRow[]
  is_empty: boolean
  override_count: number
}

export type ChangeStatus = 'DRAFT' | 'SUBMITTED' | 'APPROVED' | 'REJECTED' | 'CANCELLED'

export interface ChangeItem {
  item_id: number
  request_id: number
  target_document_id: number
  section_number: number
  target_table: string
  target_record_id: number | null
  target_field: string
  original_value: string | null
  proposed_value: string | null
  clears_value: number
  change_comment: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface ChangeEvent {
  event_id: number
  request_id: number
  event_type: string
  from_status: ChangeStatus | null
  to_status: ChangeStatus | null
  event_comment: string | null
  actor: string
  created_at: string
}

export interface ChangeRequestSummary {
  request_id: number
  document_id: number
  title: string
  reason: string | null
  status: ChangeStatus
  created_by: string
  created_at: string
  updated_at: string
  submitted_by: string | null
  submitted_at: string | null
  decided_by: string | null
  decided_at: string | null
  decision_comment: string | null
  filename: string | null
  customer: string | null
  spec_number: string | null
  item: string | null
  item_count: number
}

export interface ChangeRequestDetail extends ChangeRequestSummary {
  items: ChangeItem[]
  events: ChangeEvent[]
  can_edit: boolean
  can_submit: boolean
  can_decide: boolean
}

export interface SpecChangeHistoryItem extends ChangeItem {
  title: string
  status: ChangeStatus
  submitted_by: string | null
  submitted_at: string | null
  decided_by: string | null
  decided_at: string | null
  decision_comment: string | null
}

export interface SpecChangeHistory {
  document_id: number
  items: SpecChangeHistoryItem[]
  requests: ChangeRequestSummary[]
}

export interface Health {
  status: 'ok' | 'unavailable'
  detail: string | null
  database: {
    dialect: string
    staging_source: string
    staging_is_readonly: boolean
    document_count: number
  } | null
  user: { email: string; is_approver: boolean } | null
}

export interface AdminStagingStatus {
  summary: {
    total_documents: number
    present_documents: number
    missing_documents: number
    parser_versions: number
    mapped_tables: number
    supplemental_tables: number
    unmapped_tables: number
    error_tables: number
    ingestion_errors: number
    parser_version_breakdown: { parser_version: string; document_count: number }[]
    last_import: string | null
  }
  needs_attention: StagingStatus[]
  change_request_counts: Record<string, number>
}

export interface AdminExceptions {
  worklist: {
    relative_path: string
    source_table_index: number | null
    detected_section: string | null
    status: string
    mapping_method: string | null
    mapping_confidence: number | null
    details: string | null
  }[]
  unmapped_tables: {
    id: number
    document_id: number
    relative_path: string
    source_table_index: number | null
    preceding_heading: string | null
    signature: string | null
    classification: string | null
    suggested_section: string | null
    mapping_method: string | null
  }[]
  ingestion_errors: {
    id: number
    relative_path: string | null
    filename: string
    error_type: string | null
    error_message: string | null
    created_at: string
  }[]
}

/** What the user is proposing to change, handed to the change drawer. */
export interface ChangeTarget {
  documentId: number
  sectionNumber: number
  sectionLabel: string
  recordId: number | null
  field: string
  fieldLabel: string
  currentValue: string | null
  rowDescription: string | null
}
