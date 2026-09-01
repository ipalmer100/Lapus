import type { ChangeStatus } from '../types'

const LABELS: Record<ChangeStatus, string> = {
  DRAFT: 'Draft',
  SUBMITTED: 'Awaiting review',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  CANCELLED: 'Cancelled',
}

export function StatusChip({ status }: { status: ChangeStatus }) {
  return <span className={`chip status-${status.toLowerCase()}`}>{LABELS[status]}</span>
}
