# Lapus Product Requirements

## Users
Primary users may include Quality, Operations, Manufacturing, Supply Chain, Engineering, Specification Management, and administrators.

## Core jobs
### Find a specification
Users can search by customer, spec, finished-good item, source filename, structure, and raw material.

### Read a specification
Users can view a complete specification in the same logical order as the original document without needing to understand database tables.

### Propose a change
A user can select a specific field or row, see the staged/original value, enter a proposed value and reason, and add it to a draft change request.

### Govern a change
A draft can be submitted. An authorized reviewer can approve or reject it. Every workflow event is auditable.

### Understand provenance
Users can always tell:
- what came from the Word source
- what Lapus proposes or has approved
- who changed it
- when it changed
- why it changed

## Main screens
1. **Specification Explorer**
   - Search/filter panel
   - Results table
   - Recent specs optional

2. **Specification Workspace**
   - Product header
   - Source metadata
   - 11-section navigation
   - Current + approved-overlay display
   - Propose-change actions

3. **Draft Change Request**
   - Request summary
   - Multiple change items
   - Original/proposed comparison
   - Submit

4. **Approval Queue**
   - Submitted requests
   - Request details
   - Approve / Reject with comments

5. **Change History**
   - Spec-level history
   - Request-level timeline

6. **Admin / Parser Health**
   - Document staging status
   - Ingestion errors
   - Unmapped/supplemental tables
   - Mapping confidence

## Section rendering
### T01 Product Description
Card/form.

### T02 Locations
Card/form.

### T03 Bill of Materials
Table. Important columns: basis weight, range, caliper, raw material, supplier, item code.

### T04 Secondary Approved Materials
Table similar to BOM.

### T05 Process Routing
Ordered table by source row/pass.

### T06 Physical Attributes & Testing
Quality matrix with pass, attribute, units, lower/upper controls/spec limits, target, procedure, frequency, notes.

### T07 Slitting Information
Grouped form/card.

### T08 Packing Information
Grouped form/card.

### T09 Reporting Requirements
Grouped form/card.

### T10 Customer Sampling Requirements
Grouped form/card.

### T11 Revision History
Read-only chronological table/timeline. This is Word-source history, not Lapus workflow history.

## Editing rules
- Do not modify staging values.
- Original value must be captured at time the change item is created.
- Proposed value may be null only when representing an intentional clear/delete; UI must make that explicit.
- Every change item identifies the target table, target row, and target column.
- Workflow changes are auditable.

## Non-goals for MVP
- Writing back to Word documents.
- Replacing the parser.
- Automatically publishing approved changes into T01-T11.
- Full enterprise identity/SSO implementation.
- Complex role administration.
