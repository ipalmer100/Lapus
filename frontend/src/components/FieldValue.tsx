// Renders one specification field.
//
// This component is where the product's central promise lives: an approved
// Lapus change is shown *over* the staged value, never instead of it. When a
// field is overridden the effective value leads, the Word-source value stays
// visible struck through beside it, and hovering or expanding gives who
// approved it and when.
//
// Because every spec field renders through here, that behaviour cannot be
// forgotten in one section and honoured in another.

import { useState } from 'react'
import type { FieldValue as FieldValueType } from '../types'

export function humanizeField(field: string): string {
  // Column names are for the database; users read specifications. A handful of
  // manufacturing abbreviations would come out wrong under plain title-casing,
  // so they are spelled out.
  const special: Record<string, string> = {
    coa: 'COA', lsl: 'LSL', lcl: 'LCL', ucl: 'UCL', usl: 'USL',
    od: 'OD', id: 'ID', ft: 'ft', mils: 'mils',
    caliper_mils: 'Caliper (mils)',
    lineal_ft_per_roll: 'Lineal ft per roll',
    coa_required: 'COA required',
    coa_recipients: 'COA recipients',
    coa_format: 'COA format',
    coa_frequency: 'COA frequency',
    values_to_report_on_coa: 'Values to report on COA',
    raw_material_item_code: 'Raw material item code',
    maximum_od: 'Maximum OD',
    core_id: 'Core ID',
    pass_name: 'Pass',
    splice_stamp_flag: 'Splice stamp',
  }
  if (special[field]) return special[field]
  return field
    .split('_')
    .map((word) => (special[word] ? special[word] : word.charAt(0).toUpperCase() + word.slice(1)))
    .join(' ')
}

function displayValue(value: string | null): string {
  if (value === null || value === '') return '—'
  return value
}

export function FieldValue({ field }: { field: FieldValueType }) {
  const [showDetail, setShowDetail] = useState(false)

  if (!field.is_overridden) {
    const empty = field.value === null || field.value === ''
    return <span className={empty ? 'value value-empty' : 'value'}>{displayValue(field.value)}</span>
  }

  const p = field.provenance
  return (
    <span className="value value-overridden">
      <span className="value-effective">
        {field.provenance?.cleared ? <em className="value-cleared">cleared</em> : displayValue(field.value)}
      </span>
      <span className="value-source" title="Value in the source Word document">
        {displayValue(field.source_value)}
      </span>
      <button
        type="button"
        className="provenance-toggle"
        aria-expanded={showDetail}
        onClick={() => setShowDetail((open) => !open)}
        title="Approved Lapus change - show details"
      >
        &#9432;
      </button>
      {showDetail && p && (
        <span className="provenance-detail">
          <strong>Approved change</strong>
          <span>Request #{p.request_id}: {p.request_title}</span>
          <span>Proposed by {p.changed_by}</span>
          {p.approved_by && <span>Approved by {p.approved_by}</span>}
          {p.comment && <span className="provenance-comment">&ldquo;{p.comment}&rdquo;</span>}
          <span className="provenance-note">
            The source document still reads &ldquo;{displayValue(p.original_value)}&rdquo;.
          </span>
        </span>
      )}
    </span>
  )
}
