// Capturing one proposed change.
//
// Everything a change item needs is shown before it is saved: which section
// and row is being changed, what the specification says now, what is being
// proposed, and why. The current value is displayed read-only -- it is
// captured server-side at this moment, so a reviewer can later tell whether
// the source has moved underneath the proposal.
//
// A change is always attached to a change request. If none is open, one is
// created here so the user never has to make an empty container first.

import { useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { ChangeRequestSummary, ChangeTarget } from '../../types'

interface Props {
  target: ChangeTarget
  openDrafts: ChangeRequestSummary[]
  onClose: () => void
  onSaved: (requestId: number) => void
}

export function ProposeChangeDrawer({ target, openDrafts, onClose, onSaved }: Props) {
  const drafts = openDrafts.filter((d) => d.document_id === target.documentId)
  const [requestId, setRequestId] = useState<number | 'new'>(drafts[0]?.request_id ?? 'new')
  const [newTitle, setNewTitle] = useState('')
  const [proposed, setProposed] = useState(target.currentValue ?? '')
  const [clears, setClears] = useState(false)
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      let id = requestId
      if (id === 'new') {
        const title = newTitle.trim() || `${target.sectionLabel} change`
        const created = await api.createRequest({ document_id: target.documentId, title })
        id = created.request_id
      }
      await api.addItem(id as number, {
        section_number: target.sectionNumber,
        target_record_id: target.recordId,
        target_field: target.field,
        proposed_value: clears ? null : proposed,
        clears_value: clears,
        change_comment: comment.trim() || null,
      })
      onSaved(id as number)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save the change.')
      setSaving(false)
    }
  }

  const unchanged = !clears && proposed === (target.currentValue ?? '')

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Propose a change">
        <header className="drawer-head">
          <h2>Propose a change</h2>
          <button type="button" className="drawer-close" onClick={onClose} aria-label="Close">&times;</button>
        </header>

        <div className="drawer-body">
          <dl className="target-summary">
            <div><dt>Section</dt><dd>{target.sectionLabel}</dd></div>
            {target.rowDescription && <div><dt>Row</dt><dd>{target.rowDescription}</dd></div>}
            <div><dt>Field</dt><dd>{target.fieldLabel}</dd></div>
          </dl>

          <label className="drawer-field">
            <span>Current value in the specification</span>
            <output className="current-value">{target.currentValue || '(empty)'}</output>
          </label>

          <label className="drawer-field">
            <span>Proposed value</span>
            <textarea
              value={clears ? '' : proposed}
              disabled={clears}
              rows={3}
              onChange={(e) => setProposed(e.target.value)}
              autoFocus
            />
          </label>

          <label className="drawer-check">
            <input type="checkbox" checked={clears} onChange={(e) => setClears(e.target.checked)} />
            {/* An intentional clear has to be explicit -- an empty box would
                otherwise be indistinguishable from an unfinished edit. */}
            <span>Clear this field (propose that it should be empty)</span>
          </label>

          <label className="drawer-field">
            <span>Reason for the change</span>
            <textarea
              value={comment}
              rows={2}
              placeholder="Why is this changing? Reviewers see this."
              onChange={(e) => setComment(e.target.value)}
            />
          </label>

          <fieldset className="drawer-fieldset">
            <legend>Add to change request</legend>
            {drafts.map((draft) => (
              <label key={draft.request_id} className="drawer-radio">
                <input
                  type="radio"
                  name="request"
                  checked={requestId === draft.request_id}
                  onChange={() => setRequestId(draft.request_id)}
                />
                <span>{draft.title} <span className="muted">({draft.item_count} change{draft.item_count === 1 ? '' : 's'})</span></span>
              </label>
            ))}
            <label className="drawer-radio">
              <input
                type="radio"
                name="request"
                checked={requestId === 'new'}
                onChange={() => setRequestId('new')}
              />
              <span>Start a new change request</span>
            </label>
            {requestId === 'new' && (
              <input
                type="text"
                className="drawer-title-input"
                placeholder={`${target.sectionLabel} change`}
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
              />
            )}
          </fieldset>

          {error && <div className="error-banner">{error}</div>}
          {unchanged && !error && (
            <p className="drawer-hint">Change the proposed value, or tick “clear this field”.</p>
          )}
        </div>

        <footer className="drawer-foot">
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="primary" disabled={saving || unchanged} onClick={() => void save()}>
            {saving ? 'Saving…' : 'Add to change request'}
          </button>
        </footer>
      </aside>
    </div>
  )
}
