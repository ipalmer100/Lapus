// The only place that talks to the backend.
//
// Relative URLs throughout: in the packaged app the API and the UI are served
// from one origin, and Vite proxies /api in development, so no build-time
// base URL is needed anywhere.

import type {
  AdminExceptions, AdminStagingStatus, ChangeRequestDetail, ChangeRequestSummary,
  ChangeStatus, Health, SearchResponse, Section, SpecChangeHistory, SpecDetail,
} from '../types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    // The packaged app's server is a console window the user can close; say so
    // rather than surfacing a bare "Failed to fetch".
    throw new ApiError(0, 'Cannot reach Lapus. Check that the app is still running.')
  }

  if (response.status === 204) return undefined as T
  const body = await response.text()
  const parsed = body ? JSON.parse(body) : null

  if (!response.ok) {
    // FastAPI puts the human-readable reason in `detail`; the service layer
    // wrote it to be shown to a user, so it is safe to display verbatim.
    const detail = typeof parsed?.detail === 'string'
      ? parsed.detail
      : `Request failed (${response.status})`
    throw new ApiError(response.status, detail)
  }
  return parsed as T
}

function queryString(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '' && value !== false) {
      search.set(key, String(value))
    }
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}

export interface SearchParams {
  q?: string
  customer?: string
  spec_number?: string
  item?: string
  filename?: string
  structure?: string
  raw_material?: string
  include_missing?: boolean
  limit?: number
  offset?: number
}

export const api = {
  health: () => request<Health>('/api/health'),

  searchSpecs: (params: SearchParams) =>
    request<SearchResponse>(`/api/specs${queryString({ ...params })}`),

  getSpec: (documentId: number) => request<SpecDetail>(`/api/specs/${documentId}`),

  getSection: (documentId: number, sectionNumber: number) =>
    request<Section>(`/api/specs/${documentId}/sections/${sectionNumber}`),

  getSpecHistory: (documentId: number) =>
    request<SpecChangeHistory>(`/api/specs/${documentId}/changes`),

  listRequests: (params: { status?: ChangeStatus; document_id?: number; mine?: boolean } = {}) =>
    request<ChangeRequestSummary[]>(`/api/change-requests${queryString({ ...params })}`),

  getRequest: (requestId: number) =>
    request<ChangeRequestDetail>(`/api/change-requests/${requestId}`),

  createRequest: (body: { document_id: number; title: string; reason?: string | null }) =>
    request<ChangeRequestDetail>('/api/change-requests', {
      method: 'POST', body: JSON.stringify(body),
    }),

  addItem: (requestId: number, body: {
    section_number: number
    target_record_id: number | null
    target_field: string
    proposed_value: string | null
    clears_value: boolean
    change_comment: string | null
  }) => request<unknown>(`/api/change-requests/${requestId}/items`, {
    method: 'POST', body: JSON.stringify(body),
  }),

  updateItem: (requestId: number, itemId: number, body: {
    proposed_value: string | null
    clears_value: boolean
    change_comment: string | null
  }) => request<unknown>(`/api/change-requests/${requestId}/items/${itemId}`, {
    method: 'PATCH', body: JSON.stringify(body),
  }),

  deleteItem: (requestId: number, itemId: number) =>
    request<void>(`/api/change-requests/${requestId}/items/${itemId}`, { method: 'DELETE' }),

  submitRequest: (requestId: number) =>
    request<ChangeRequestDetail>(`/api/change-requests/${requestId}/submit`, { method: 'POST' }),

  approveRequest: (requestId: number, comment: string | null) =>
    request<ChangeRequestDetail>(`/api/change-requests/${requestId}/approve`, {
      method: 'POST', body: JSON.stringify({ comment }),
    }),

  rejectRequest: (requestId: number, comment: string) =>
    request<ChangeRequestDetail>(`/api/change-requests/${requestId}/reject`, {
      method: 'POST', body: JSON.stringify({ comment }),
    }),

  cancelRequest: (requestId: number, comment: string | null) =>
    request<ChangeRequestDetail>(`/api/change-requests/${requestId}/cancel`, {
      method: 'POST', body: JSON.stringify({ comment }),
    }),

  adminStagingStatus: () => request<AdminStagingStatus>('/api/admin/staging-status'),
  adminExceptions: () => request<AdminExceptions>('/api/admin/exceptions'),
}
