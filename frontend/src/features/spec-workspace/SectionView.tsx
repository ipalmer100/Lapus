// Renders one specification section in whatever shape suits it.
//
// The layout comes from config/spec_sections.json via the API, not from a
// switch on table names here, so adding or reshaping a section is a config
// change. Four layouts cover all eleven sections:
//
//   form           single record, read as a labelled card (product, locations, ...)
//   table          repeating rows (bill of materials, secondary materials, routing)
//   quality_matrix repeating rows with limit columns grouped for scanning (testing)
//   timeline       chronological, read-only (revision history)

import type { Section, SectionRow, ChangeTarget } from '../../types'
import { FieldValue, humanizeField } from '../../components/FieldValue'

interface Props {
  section: Section
  documentId: number
  canPropose: boolean
  onPropose: (target: ChangeTarget) => void
}

/** A short human label for one row, so a change drawer can say what is being
 *  changed without making the user remember a row number. */
function describeRow(section: Section, row: SectionRow): string | null {
  const pick = (field: string) => row.fields[field]?.value ?? null
  switch (section.table) {
    case 't03_bill_of_materials':
    case 't04_secondary_approved_materials':
      return pick('raw_material') ?? `Row ${row.identity.source_row ?? ''}`
    case 't05_process_routing':
      return [pick('pass'), pick('process')].filter(Boolean).join(' - ') || null
    case 't06_physical_attributes_testing':
      return [pick('pass_name'), pick('attribute')].filter(Boolean).join(' - ') || null
    case 't11_revision_history':
      return `Revision ${pick('revision_number') ?? ''}`
    default:
      return null
  }
}

function EmptySection({ label }: { label: string }) {
  // A missing section is a legitimate state for a legacy document, not a
  // failure (AGENTS.md rule 7).
  return (
    <p className="section-empty">
      This specification has no {label.toLowerCase()} information.
    </p>
  )
}

function ProposeButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="propose-button" onClick={onClick} title="Propose a change">
      Propose change
    </button>
  )
}

export function SectionView({ section, documentId, canPropose, onPropose }: Props) {
  if (section.is_empty) return <EmptySection label={section.label} />

  const propose = (row: SectionRow, field: string): ChangeTarget => ({
    documentId,
    sectionNumber: section.number,
    sectionLabel: section.label,
    recordId: row.record_id,
    field,
    fieldLabel: humanizeField(field),
    currentValue: row.fields[field]?.value ?? null,
    rowDescription: describeRow(section, row),
  })

  if (section.layout === 'form') {
    const row = section.rows[0]
    return (
      <dl className="section-form">
        {section.editable_fields.map((field) => (
          <div key={field} className="form-field">
            <dt>{humanizeField(field)}</dt>
            <dd>
              <FieldValue field={row.fields[field]} />
              {canPropose && section.is_editable && (
                <ProposeButton onClick={() => onPropose(propose(row, field))} />
              )}
            </dd>
          </div>
        ))}
      </dl>
    )
  }

  if (section.layout === 'timeline') {
    return (
      <ol className="section-timeline">
        {section.rows.map((row) => (
          <li key={row.record_id ?? row.identity.source_row}>
            <div className="timeline-marker">{row.fields.revision_number?.value ?? '—'}</div>
            <div className="timeline-body">
              <div className="timeline-head">
                <span className="timeline-date">{row.fields.revision_date?.value ?? 'Undated'}</span>
                <span className="timeline-who">{row.fields.who?.value ?? 'Unattributed'}</span>
              </div>
              <p className="timeline-text">{row.fields.revision?.value ?? '—'}</p>
            </div>
          </li>
        ))}
      </ol>
    )
  }

  // Both table layouts share a body; the quality matrix only differs in how
  // its columns are grouped and labelled.
  const columns = section.editable_fields
  const isMatrix = section.layout === 'quality_matrix'

  return (
    <div className="section-table-wrap">
      <table className={isMatrix ? 'section-table matrix' : 'section-table'}>
        <thead>
          {isMatrix && (
            // Limit columns read as a range, so they get a spanning header:
            // an operator scans LSL..USL left to right as one idea.
            <tr className="matrix-groups">
              <th colSpan={4} />
              <th colSpan={5} className="matrix-group">Limits</th>
              <th colSpan={3} />
            </tr>
          )}
          <tr>
            {columns.map((field) => (
              <th key={field} className={isMatrix && ['lsl', 'lcl', 'target', 'ucl', 'usl'].includes(field)
                ? 'limit-column' : undefined}>
                {humanizeField(field)}
              </th>
            ))}
            {canPropose && section.is_editable && <th className="actions-column" />}
          </tr>
        </thead>
        <tbody>
          {section.rows.map((row) => (
            <tr key={row.record_id ?? row.identity.source_row}
                className={row.has_overrides ? 'row-has-overrides' : undefined}>
              {columns.map((field) => (
                <td key={field}>
                  <FieldValue field={row.fields[field]} />
                  {canPropose && section.is_editable && (
                    <button
                      type="button"
                      className="cell-propose"
                      title={`Propose a change to ${humanizeField(field)}`}
                      onClick={() => onPropose(propose(row, field))}
                    >
                      &#9998;
                    </button>
                  )}
                </td>
              ))}
              {canPropose && section.is_editable && (
                <td className="actions-column">
                  {row.has_overrides && <span className="row-flag" title="Contains an approved change">&#9679;</span>}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
