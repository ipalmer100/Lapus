# Architecture

## Context diagram

```text
Desktop/Server Specs folder
       |
       v
Python V5.2 parser
       |
       v
PostgreSQL Spec_Stage
  public schema (read-only to Lapus)
       |
       +-----------------------------+
       |                             |
       v                             v
FastAPI read services        lapus schema write services
       |                             |
       +--------------+--------------+
                      |
                      v
                React frontend
```

## Backend responsibilities
- Database connection pooling.
- Authentication identity integration.
- Authorization checks.
- Search and section retrieval.
- Change-request workflow.
- Server-side validation of target table/field against allowlists.
- Effective-value overlay calculation.
- Audit/event creation.

## Frontend responsibilities
- Search/navigation.
- Human-friendly section presentation.
- Field selection and edit dialogs.
- Change-request composition.
- Workflow UI.
- Clear provenance display.

## Generic target model
A change item should point to a source field without directly changing it.

Repeating row example:
```json
{
  "target_table": "t03_bill_of_materials",
  "target_record_id": 12984,
  "target_document_id": 431,
  "target_field": "supplier",
  "original_value": "Supplier A",
  "proposed_value": "Supplier B"
}
```

Single-row example:
```json
{
  "target_table": "t01_product_description",
  "target_record_id": null,
  "target_document_id": 431,
  "target_field": "structure_description",
  "original_value": "...",
  "proposed_value": "..."
}
```

## Overlay rule
The source/staged value remains authoritative for provenance. Lapus can display the latest APPROVED change item as an effective overlay.

The UI should show both:
- Source value
- Effective approved value (when different)

Do not hide the source value.

## Search strategy
Build server-side PostgreSQL queries. Search the spec list first, then fetch sections only for a selected `document_id`.

Raw material search should query T03 and T04 and return matching document IDs rather than loading all material rows into the browser.
