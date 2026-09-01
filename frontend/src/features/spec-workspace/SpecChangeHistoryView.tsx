// Every Lapus change ever proposed against this specification.
//
// Deliberately separate from section 11: that is the Word document's own
// revision history, written by whoever maintained the document. This is the
// application's workflow record. Conflating the two would misrepresent both
// (AGENTS.md rule 8).

import type { SpecChangeHistory } from '../../types'
import { humanizeField } from '../../components/FieldValue'
import { StatusChip } from '../../components/StatusChip'

export function SpecChangeHistoryView({ history }: { history: SpecChangeHistory | null }) {
  if (!history) return <div className="loading">Loading change history…</div>

  if (history.items.length === 0) {
    return (
      <div className="history-panel">
        <h3>Lapus change history</h3>
        <p className="section-empty">No changes have been proposed for this specification.</p>
      </div>
    )
  }

  return (
    <div className="history-panel">
      <h3>Lapus change history</h3>
      <p className="panel-note">
        Changes proposed in Lapus. The source document&rsquo;s own revision history is section 11.
      </p>
      <table className="history-table">
        <thead>
          <tr>
            <th>Request</th><th>Field</th><th>From</th><th>To</th>
            <th>Status</th><th>Proposed by</th><th>Decided by</th>
          </tr>
        </thead>
        <tbody>
          {history.items.map((item) => (
            <tr key={item.item_id}>
              <td>#{item.request_id} {item.title}</td>
              <td>{humanizeField(item.target_field)}</td>
              <td className="from-value">{item.original_value || <span className="muted">(empty)</span>}</td>
              <td className="to-value">
                {item.clears_value ? <em>cleared</em> : (item.proposed_value || <span className="muted">(empty)</span>)}
              </td>
              <td><StatusChip status={item.status} /></td>
              <td>{item.created_by}</td>
              <td>{item.decided_by ?? <span className="muted">—</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
