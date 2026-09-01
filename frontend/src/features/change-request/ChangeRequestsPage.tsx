// Change requests: the list, and one request's detail with its items and timeline.
//
// A draft is editable by its author until submitted. Submission freezes the
// items so a reviewer approves exactly what they read.

import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { ChangeRequestDetail, ChangeRequestSummary, ChangeStatus } from '../../types'
import { humanizeField } from '../../components/FieldValue'
import { StatusChip } from '../../components/StatusChip'

const FILTERS: { label: string; status?: ChangeStatus }[] = [
  { label: 'All' },
  { label: 'Drafts', status: 'DRAFT' },
  { label: 'Awaiting review', status: 'SUBMITTED' },
  { label: 'Approved', status: 'APPROVED' },
  { label: 'Rejected', status: 'REJECTED' },
]

interface Props {
  onOpenSpec: (documentId: number) => void
  onChanged: () => void
  selectedRequestId: number | null
  onSelectRequest: (requestId: number | null) => void
}

export function ChangeRequestsPage({ onOpenSpec, onChanged, selectedRequestId, onSelectRequest }: Props) {
  const [filter, setFilter] = useState<ChangeStatus | undefined>(undefined)
  const [requests, setRequests] = useState<ChangeRequestSummary[]>([])
  const [detail, setDetail] = useState<ChangeRequestDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const loadList = useCallback(async () => {
    try {
      setRequests(await api.listRequests(filter ? { status: filter } : {}))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load change requests.')
    }
  }, [filter])

  useEffect(() => { void loadList() }, [loadList])

  const loadDetail = useCallback(async (id: number) => {
    try {
      setDetail(await api.getRequest(id))
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load that change request.')
    }
  }, [])

  useEffect(() => {
    if (selectedRequestId === null) { setDetail(null); return }
    void loadDetail(selectedRequestId)
  }, [selectedRequestId, loadDetail])

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await action()
      if (selectedRequestId !== null) await loadDetail(selectedRequestId)
      await loadList()
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'That action could not be completed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="requests-page">
      <div className="requests-list">
        <div className="filter-tabs">
          {FILTERS.map((f) => (
            <button
              key={f.label}
              type="button"
              className={filter === f.status ? 'active' : ''}
              onClick={() => setFilter(f.status)}
            >
              {f.label}
            </button>
          ))}
        </div>

        {requests.length === 0 ? (
          <p className="empty-state">No change requests here yet.</p>
        ) : (
          <ul className="request-cards">
            {requests.map((r) => (
              <li key={r.request_id}>
                <button
                  type="button"
                  className={r.request_id === selectedRequestId ? 'request-card active' : 'request-card'}
                  onClick={() => onSelectRequest(r.request_id)}
                >
                  <span className="request-card-head">
                    <span className="request-title">#{r.request_id} {r.title}</span>
                    <StatusChip status={r.status} />
                  </span>
                  <span className="request-card-meta">
                    {r.spec_number ?? r.filename} &middot; {r.customer ?? 'Customer not stated'}
                  </span>
                  <span className="request-card-meta muted">
                    {r.item_count} change{r.item_count === 1 ? '' : 's'} &middot; by {r.created_by}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="request-detail">
        {error && <div className="error-banner">{error}</div>}
        {!detail ? (
          <p className="empty-state">Select a change request to see its details.</p>
        ) : (
          <RequestDetail
            detail={detail}
            busy={busy}
            onOpenSpec={onOpenSpec}
            onAct={act}
          />
        )}
      </div>
    </div>
  )
}

function RequestDetail({ detail, busy, onOpenSpec, onAct }: {
  detail: ChangeRequestDetail
  busy: boolean
  onOpenSpec: (documentId: number) => void
  onAct: (action: () => Promise<unknown>) => Promise<void>
}) {
  const [decisionComment, setDecisionComment] = useState('')

  return (
    <>
      <header className="request-head">
        <div>
          <h2>#{detail.request_id} {detail.title}</h2>
          <p className="muted">
            <button type="button" className="link-button" onClick={() => onOpenSpec(detail.document_id)}>
              {detail.spec_number ?? detail.filename}
            </button>
            {' '}&middot; {detail.customer ?? 'Customer not stated'} &middot; raised by {detail.created_by}
          </p>
          {detail.reason && <p className="request-reason">{detail.reason}</p>}
        </div>
        <StatusChip status={detail.status} />
      </header>

      <h3>Proposed changes</h3>
      {detail.items.length === 0 ? (
        <p className="section-empty">
          Nothing proposed yet. Open the specification and choose &ldquo;Propose change&rdquo; on a field.
        </p>
      ) : (
        <table className="items-table">
          <thead>
            <tr><th>Section</th><th>Field</th><th>Current</th><th>Proposed</th><th>Reason</th>{detail.can_edit && <th />}</tr>
          </thead>
          <tbody>
            {detail.items.map((item) => (
              <tr key={item.item_id}>
                <td>{String(item.section_number).padStart(2, '0')}</td>
                <td>{humanizeField(item.target_field)}</td>
                <td className="from-value">{item.original_value || <span className="muted">(empty)</span>}</td>
                <td className="to-value">
                  {item.clears_value ? <em>cleared</em> : (item.proposed_value || <span className="muted">(empty)</span>)}
                </td>
                <td className="muted">{item.change_comment ?? '—'}</td>
                {detail.can_edit && (
                  <td>
                    <button
                      type="button"
                      className="link-button danger"
                      disabled={busy}
                      onClick={() => void onAct(() => api.deleteItem(detail.request_id, item.item_id))}
                    >
                      Remove
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="request-actions">
        {detail.can_submit && (
          <button type="button" className="primary" disabled={busy}
                  onClick={() => void onAct(() => api.submitRequest(detail.request_id))}>
            Submit for review
          </button>
        )}
        {detail.can_decide && (
          <div className="decision-panel">
            <label>
              <span>Decision comment</span>
              <textarea rows={2} value={decisionComment}
                        placeholder="Required when rejecting"
                        onChange={(e) => setDecisionComment(e.target.value)} />
            </label>
            <div className="decision-buttons">
              <button type="button" className="primary" disabled={busy}
                      onClick={() => void onAct(() => api.approveRequest(detail.request_id, decisionComment || null))}>
                Approve
              </button>
              <button type="button" className="danger" disabled={busy || !decisionComment.trim()}
                      onClick={() => void onAct(() => api.rejectRequest(detail.request_id, decisionComment))}>
                Reject
              </button>
            </div>
          </div>
        )}
        {(detail.status === 'DRAFT' || detail.status === 'SUBMITTED') && (
          <button type="button" className="secondary" disabled={busy}
                  onClick={() => void onAct(() => api.cancelRequest(detail.request_id, null))}>
            Cancel request
          </button>
        )}
      </div>

      {detail.status === 'APPROVED' && (
        <p className="overlay-note">
          Approved. These values now appear over the staged specification, with the
          original Word values still shown alongside them.
        </p>
      )}

      <h3>Audit trail</h3>
      <ol className="event-timeline">
        {detail.events.map((event) => (
          <li key={event.event_id}>
            <span className="event-type">{event.event_type.replace(/_/g, ' ').toLowerCase()}</span>
            <span className="event-actor">{event.actor}</span>
            <span className="event-time">{event.created_at}</span>
            {event.event_comment && <span className="event-comment">{event.event_comment}</span>}
          </li>
        ))}
      </ol>
    </>
  )
}
