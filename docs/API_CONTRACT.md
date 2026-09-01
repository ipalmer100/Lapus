# Suggested API Contract

This is an implementation target, not a requirement to preserve exact route names.

## Specs
`GET /api/specs?q=&customer=&item=&raw_material=&limit=&offset=`

Returns lightweight search rows.

`GET /api/specs/{document_id}`

Returns product header, source metadata, parser status, and section availability.

`GET /api/specs/{document_id}/sections/{section_number}`

Returns one section in a stable JSON shape.

`GET /api/specs/{document_id}/changes`

Returns Lapus change requests/items affecting the spec.

## Change requests
`POST /api/change-requests`

Create DRAFT request.

`GET /api/change-requests/{request_id}`

Return request, items, and event timeline.

`POST /api/change-requests/{request_id}/items`

Add field-level change item.

`PATCH /api/change-requests/{request_id}/items/{item_id}`

Edit DRAFT item.

`DELETE /api/change-requests/{request_id}/items/{item_id}`

Delete DRAFT item.

`POST /api/change-requests/{request_id}/submit`

DRAFT -> SUBMITTED.

`POST /api/change-requests/{request_id}/approve`

SUBMITTED -> APPROVED.

`POST /api/change-requests/{request_id}/reject`

SUBMITTED -> REJECTED.

## Admin
`GET /api/admin/staging-status`

`GET /api/admin/exceptions`

## Response behavior
- 404 for unknown document/request.
- 409 for invalid workflow transition or stale edit.
- 422 for invalid target table/field or validation errors.
- Never expose database credentials or raw server traces to the browser.
