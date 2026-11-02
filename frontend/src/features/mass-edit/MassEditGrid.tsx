// One section across every specification in scope, edited as a grid.
//
// Cobalt's Mass Edit, with Lapus's boundary kept intact. Nothing here writes
// to specification data: cells are read-only until Edit is pressed, changes
// are held in the browser, and the batch becomes a single change request that
// still goes through review. The grid is a faster way to compose a change
// request, not a way around one.
//
// The scope is the sidebar's filter, not a separate one. Cobalt's rule is that
// a fill cannot touch a spec that is out of scope, and that only holds if both
// views are filtered by the same thing.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type {
  BulkProposal, ChangeRequestSummary, SectionGrid, SectionMeta, SpecFilter,
} from '../../types'
import { blank } from '../../display'
import { humanizeField } from '../../components/FieldValue'

const PAGE = 200

interface Props {
  filter: SpecFilter
  sections: SectionMeta[]
  openDrafts: ChangeRequestSummary[]
  onStaged: (requestId: number) => void
}

interface Draft {
  value: string
  original: string
}

/** Identifies one cell. record_id is null for single-record sections. */
function cellKey(documentId: number, recordId: number | null, field: string): string {
  return `${documentId}|${recordId ?? ''}|${field}`
}

interface DragState {
  field: string
  sourceKey: string
  sourceValue: string
  startIndex: number
  currentIndex: number
}

export function MassEditGrid({ filter, sections, openDrafts, onStaged }: Props) {
  const editable = useMemo(() => sections.filter((s) => s.is_editable), [sections])
  const [sectionNumber, setSectionNumber] = useState<number>(() => {
    // Single-record sections make an honest one-row-per-spec grid; repeating
    // ones flatten to many rows per spec and are a harder read, so the default
    // lands on a single-record section.
    const single = sections.find((s) => s.is_editable && !s.is_repeating)
    return single?.number ?? 1
  })
  const [grid, setGrid] = useState<SectionGrid | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editing, setEditing] = useState(false)
  const [drafts, setDrafts] = useState<Map<string, Draft>>(new Map())
  const [dragging, setDragging] = useState<DragState | null>(null)
  const [saving, setSaving] = useState(false)
  const [requestId, setRequestId] = useState<number | 'new'>('new')
  const [newTitle, setNewTitle] = useState('')

  const seq = useRef(0)

  const load = useCallback(async () => {
    const id = ++seq.current
    setLoading(true)
    setError(null)
    try {
      const result = await api.getSectionGrid(sectionNumber, {
        q: filter.query || undefined,
        raw_material: filter.material || undefined,
        include_missing: filter.includeMissing,
        limit: PAGE,
      })
      if (id !== seq.current) return
      setGrid(result)
    } catch (err) {
      if (id !== seq.current) return
      setError(err instanceof ApiError ? err.message : 'Could not load the grid.')
      setGrid(null)
    } finally {
      if (id === seq.current) setLoading(false)
    }
  }, [sectionNumber, filter])

  useEffect(() => { void load() }, [load])

  // Leaving edit mode is tied to what is on screen: switching section or scope
  // mid-edit would strand drafts against rows that are no longer there.
  useEffect(() => {
    setEditing(false)
    setDrafts(new Map())
  }, [sectionNumber, filter])

  const rows = useMemo(() => grid?.rows ?? [], [grid])

  const stage = useCallback((key: string, value: string, original: string) => {
    setDrafts((prev) => {
      const next = new Map(prev)
      if (value === original) next.delete(key)
      else next.set(key, { value, original })
      return next
    })
  }, [])

  /** Fill-handle drag: stages one value down a column, still unwritten. */
  const stageFill = useCallback((drag: DragState) => {
    const lo = Math.min(drag.startIndex, drag.currentIndex)
    const hi = Math.max(drag.startIndex, drag.currentIndex)
    setDrafts((prev) => {
      const next = new Map(prev)
      for (const row of rows.slice(lo, hi + 1)) {
        const key = cellKey(row.document_id, row.record_id, drag.field)
        if (key === drag.sourceKey) continue
        const original = row.fields[drag.field]?.value ?? ''
        if (drag.sourceValue === original) next.delete(key)
        else next.set(key, { value: drag.sourceValue, original })
      }
      return next
    })
  }, [rows])

  // Drag tracking lives on the window so the pointer can leave the cell it
  // started in, which it always does.
  useEffect(() => {
    if (!dragging) return
    let frame = 0
    let pending: MouseEvent | null = null

    const process = (event: MouseEvent) => {
      const element = document.elementFromPoint(event.clientX, event.clientY)
      const row = (element as HTMLElement | null)?.closest('tr[data-row-index]')
      const index = row?.getAttribute('data-row-index')
      if (index == null) return
      setDragging((prev) => (prev ? { ...prev, currentIndex: Number(index) } : prev))
    }
    const onMove = (event: MouseEvent) => {
      pending = event
      if (!frame) {
        frame = requestAnimationFrame(() => {
          frame = 0
          if (pending) process(pending)
        })
      }
    }
    const onUp = () => {
      if (frame) cancelAnimationFrame(frame)
      setDragging((current) => {
        if (current) stageFill(current)
        return null
      })
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [dragging, stageFill])

  const pending = useMemo(
    () => [...drafts.entries()].filter(([, d]) => d.value !== d.original),
    [drafts],
  )
  const affectedSpecs = useMemo(
    () => new Set(pending.map(([key]) => key.split('|')[0])).size,
    [pending],
  )

  const save = async () => {
    if (!grid || pending.length === 0) return
    setSaving(true)
    setError(null)
    try {
      let id = requestId
      if (id === 'new') {
        const title = newTitle.trim() || `${grid.section.label} — bulk change`
        const created = await api.createRequest({
          document_id: rows[0].document_id,
          title,
          reason: `${pending.length} changes across ${affectedSpecs} specifications`,
        })
        id = created.request_id
      }
      const proposals: BulkProposal[] = pending.map(([key, draft]) => {
        const [documentId, recordId, field] = key.split('|')
        return {
          document_id: Number(documentId),
          section_number: grid.section.number,
          target_record_id: recordId === '' ? null : Number(recordId),
          target_field: field,
          proposed_value: draft.value,
          clears_value: false,
          change_comment: null,
        }
      })
      await api.addItemsBulk(id as number, proposals)
      setDrafts(new Map())
      setEditing(false)
      onStaged(id as number)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not stage those changes.')
    } finally {
      setSaving(false)
    }
  }

  const fields = grid?.fields ?? []
  const section = grid?.section
  // Product Description's editable fields include the customer, so showing an
  // identity column for it too puts the same value on screen twice -- once
  // read-only and once editable, which reads as a bug.
  const showCustomerColumn = !fields.includes('customer')

  return (
    <div className="mass-edit">
      <div className="mass-edit-bar">
        <select
          className="sidebar-select"
          value={sectionNumber}
          onChange={(e) => setSectionNumber(Number(e.target.value))}
        >
          {editable.map((s) => (
            <option key={s.number} value={s.number}>
              {String(s.number).padStart(2, '0')} {s.label}
              {s.is_repeating ? ' (rows per spec)' : ''}
            </option>
          ))}
        </select>

        {grid && (
          <span className="muted">
            {grid.rows.length.toLocaleString()} row{grid.rows.length === 1 ? '' : 's'} across{' '}
            {new Set(grid.rows.map((r) => r.document_id)).size.toLocaleString()} spec
            {grid.total > grid.rows.length ? `, showing the first ${PAGE}` : ''}
          </span>
        )}

        <span className="tab-spacer" />

        {!editing ? (
          <button
            type="button"
            className="secondary"
            disabled={!grid || grid.rows.length === 0 || !section?.is_editable}
            onClick={() => setEditing(true)}
          >
            Edit
          </button>
        ) : (
          <>
            <span className="muted">
              {pending.length} change{pending.length === 1 ? '' : 's'} · {affectedSpecs} spec
              {affectedSpecs === 1 ? '' : 's'}
            </span>
            <button
              type="button"
              className="secondary"
              onClick={() => { setEditing(false); setDrafts(new Map()) }}
            >
              Cancel
            </button>
            <button
              type="button"
              className="primary"
              disabled={saving || pending.length === 0}
              onClick={() => void save()}
            >
              {saving ? 'Saving…' : 'Add to change request'}
            </button>
          </>
        )}
      </div>

      {editing && (
        <div className="mass-edit-target">
          <label className="drawer-radio">
            <input
              type="radio" name="bulk-request"
              checked={requestId === 'new'}
              onChange={() => setRequestId('new')}
            />
            <span>New change request</span>
          </label>
          {requestId === 'new' && (
            <input
              className="drawer-title-input"
              placeholder={section ? `${section.label} — bulk change` : 'Title'}
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
            />
          )}
          {openDrafts.map((draft) => (
            <label key={draft.request_id} className="drawer-radio">
              <input
                type="radio" name="bulk-request"
                checked={requestId === draft.request_id}
                onChange={() => setRequestId(draft.request_id)}
              />
              <span>
                #{draft.request_id} {draft.title} <span className="muted">({draft.item_count})</span>
              </span>
            </label>
          ))}
          <span className="muted mass-edit-note">
            Changes are proposed, not applied — they go to review like any other change request.
          </span>
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      {loading && !grid ? (
        <div className="loading">Loading…</div>
      ) : !grid || grid.rows.length === 0 ? (
        <div className="empty-state">
          No specifications in scope hold {section?.label.toLowerCase() ?? 'this section'}.
        </div>
      ) : (
        <div className="mass-edit-scroll">
          <table className="detail-table mass-edit-table">
            <thead>
              <tr>
                <th className="sticky-col">Specification</th>
                {showCustomerColumn && <th>Customer</th>}
                {fields.map((field) => <th key={field}>{humanizeField(field)}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={cellKey(row.document_id, row.record_id, '')} data-row-index={index}>
                  <td className="sticky-col">
                    {blank(row.spec_number) ?? blank(row.filename) ?? `Document ${row.document_id}`}
                  </td>
                  {showCustomerColumn && (
                    <td className="muted">{blank(row.customer) ?? '—'}</td>
                  )}
                  {fields.map((field) => {
                    const key = cellKey(row.document_id, row.record_id, field)
                    const cell = row.fields[field]
                    const original = cell?.value ?? ''
                    const draft = drafts.get(key)
                    const shown = draft?.value ?? original
                    const dirty = draft !== undefined && draft.value !== draft.original
                    const inFill =
                      dragging?.field === field &&
                      index >= Math.min(dragging.startIndex, dragging.currentIndex) &&
                      index <= Math.max(dragging.startIndex, dragging.currentIndex)

                    if (!editing) {
                      return (
                        <td key={field}>
                          {cell?.is_overridden ? (
                            <span className="value-effective" title="Carries an approved change">
                              {cell.value || '—'}
                            </span>
                          ) : (
                            original || <span className="muted">—</span>
                          )}
                        </td>
                      )
                    }
                    return (
                      <td
                        key={field}
                        className={[dirty ? 'cell-dirty' : '', inFill ? 'cell-in-fill' : '']
                          .filter(Boolean).join(' ') || undefined}
                      >
                        <input
                          className="cell-editor"
                          value={shown}
                          onChange={(e) => stage(key, e.target.value, original)}
                        />
                        <span
                          className="fill-handle"
                          title="Drag down to copy this value"
                          onMouseDown={(e) => {
                            e.preventDefault()
                            setDragging({
                              field, sourceKey: key, sourceValue: shown,
                              startIndex: index, currentIndex: index,
                            })
                          }}
                        />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
