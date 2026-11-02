"""Assembling a section for display: staged values plus approved Lapus changes.

The rule this module exists to enforce (PROJECT_CONTEXT.md, ARCHITECTURE.md):

    An approved change is shown as an *overlay*. The staged value stays visible
    and stays authoritative for provenance. Lapus never overwrites T01-T11.

So every field is emitted as a small record rather than a bare value:

    {"value": <what to show>, "source_value": <what the Word document said>,
     "is_overridden": true/false, "provenance": {...}}

The frontend can then render the effective value prominently and the original
alongside it, and no consumer can accidentally lose the distinction by reading
a plain string.
"""

from __future__ import annotations

from typing import Any

from ..catalog import Section, readable_columns
from ..db.engine import Row

# Columns that identify a row rather than carry spec content. They are passed
# through untouched -- overlaying an id would break row targeting.
_IDENTITY_COLUMNS = {"id", "document_id", "source_table_index", "source_row"}


def build_field(value: Any, override: Row | None) -> dict[str, Any]:
    """Package one field value with its provenance.

    Public because both the single-spec view and the mass-edit grid render
    fields, and both must package them identically -- a grid cell that lost
    the source value would be exactly the regression this shape prevents.
    """
    source_value = value
    if override is None:
        return {
            "value": source_value,
            "source_value": source_value,
            "is_overridden": False,
            "provenance": None,
        }

    # An item flagged clears_value proposes emptiness deliberately; without the
    # flag a NULL proposed_value would be indistinguishable from "nothing was
    # proposed" (PRODUCT_REQUIREMENTS.md, Editing rules).
    effective = None if override.get("clears_value") else override.get("proposed_value")
    return {
        "value": effective,
        "source_value": source_value,
        "is_overridden": True,
        "provenance": {
            "request_id": override.get("request_id"),
            "request_title": override.get("title"),
            "item_id": override.get("item_id"),
            "changed_by": override.get("created_by"),
            "changed_at": override.get("created_at"),
            "approved_by": override.get("decided_by"),
            "approved_at": override.get("decided_at"),
            "comment": override.get("change_comment"),
            "original_value": override.get("original_value"),
            "cleared": bool(override.get("clears_value")),
        },
    }


# Two ways to find the change item for a row, in order of precision.
#
# By surrogate key, which is exact while it lasts:
#     ("id", table, record_id, field)
# By position in the source document, which outlives a reparse:
#     ("src", table, document_id, source_table_index, source_row, field)
IdKey = tuple[str, str, int | None, str]
SourceKey = tuple[str, str, int, int, int, str]
OverlayIndex = dict[tuple, Row]


def index_approved_items(items: list[Row]) -> OverlayIndex:
    """Key approved change items by the field they target, two ways.

    `items` arrives oldest-decision-first, so later approvals overwrite earlier
    ones for the same field and the most recent decision is what the user sees.

    Both keys are stored because neither alone is sufficient. target_record_id
    is exact, but the parser DELETEs and reinserts a document's rows on every
    rerun and the surrogate key is regenerated -- so an overlay keyed only on
    it silently stops applying after a reparse, which is precisely what
    AGENTS.md rule 6 forbids. The row's position in the source document
    survives that, and is used as the fallback.
    """
    index: OverlayIndex = {}
    for item in items:
        record_id = item.get("target_record_id")
        table = item["target_table"]
        field = item["target_field"]
        index[("id", table, int(record_id) if record_id is not None else None, field)] = item

        table_index = item.get("target_source_table_index")
        source_row = item.get("target_source_row")
        if table_index is not None and source_row is not None:
            index[(
                "src", table, int(item["target_document_id"]),
                int(table_index), int(source_row), field,
            )] = item
    return index


def find_override(index: OverlayIndex, table: str, record_id: int | None,
                  field: str, row: Row, staged_value: Any) -> Row | None:
    """The approved change for one rendered cell, if there is one.

    Tries the surrogate key first. Falling back to the source position is
    guarded by the captured original value: a reparse that only regenerated
    ids leaves the staged value identical and the overlay reattaches, while a
    reparse that actually changed the document leaves the overlay inert rather
    than re-aiming an approved change at content nobody approved it for.
    """
    exact = index.get(("id", table, record_id, field))
    if exact is not None:
        return exact

    table_index = row.get("source_table_index")
    source_row = row.get("source_row")
    document_id = row.get("document_id")
    if table_index is None or source_row is None or document_id is None:
        return None

    candidate = index.get(
        ("src", table, int(document_id), int(table_index), int(source_row), field)
    )
    if candidate is None:
        return None

    original = candidate.get("original_value")
    current = None if staged_value is None else str(staged_value)
    if original != current:
        # The document moved on. Showing an approved value over content it was
        # never approved against would be worse than showing nothing.
        return None
    return candidate


def render_section(section: Section, rows: list[Row],
                   approved: OverlayIndex) -> dict[str, Any]:
    """Build the display payload for one section.

    Shape is stable whether or not the section has data: an absent section is
    an empty `rows` list and `is_empty`, never an error (AGENTS.md rule 7).
    """
    rendered_rows: list[dict[str, Any]] = []

    for row in rows:
        record_id = int(row["id"]) if section.is_repeating and row.get("id") is not None else None
        fields: dict[str, Any] = {}
        identity: dict[str, Any] = {}

        for column in readable_columns(section):
            value = row.get(column)
            if column in _IDENTITY_COLUMNS:
                identity[column] = value
                continue
            override = find_override(approved, section.table, record_id, column, row, value)
            fields[column] = build_field(value, override)

        rendered_rows.append({
            "record_id": record_id,
            "identity": identity,
            "fields": fields,
            # True when any field on this row carries an approved change, so a
            # table row can be flagged without the caller scanning every field.
            "has_overrides": any(f["is_overridden"] for f in fields.values()),
        })

    return {
        "number": section.number,
        "key": section.key,
        "label": section.label,
        "layout": section.layout,
        "table": section.table,
        "primary_key": section.primary_key,
        "is_repeating": section.is_repeating,
        "is_editable": section.is_editable,
        "editable_fields": list(section.editable_fields),
        "rows": rendered_rows,
        "is_empty": not rendered_rows,
        "override_count": sum(
            1 for r in rendered_rows for f in r["fields"].values() if f["is_overridden"]
        ),
    }


def source_coordinates(rows: list[Row], section: Section,
                       record_id: int | None) -> tuple[int | None, int | None]:
    """Where a targeted row sits in the source document.

    Returns (None, None) for single-record sections: they are keyed on
    document_id, which the parser preserves, so they never needed a fallback.
    """
    if not section.is_repeating:
        return None, None
    for row in rows:
        if row.get("id") is not None and int(row["id"]) == record_id:
            table_index = row.get("source_table_index")
            source_row = row.get("source_row")
            return (
                int(table_index) if table_index is not None else None,
                int(source_row) if source_row is not None else None,
            )
    return None, None


def current_value(rows: list[Row], section: Section, record_id: int | None,
                  field: str) -> tuple[bool, Any]:
    """The staged value of one field, for capturing `original_value`.

    Returns (found, value). `found` distinguishes "the row exists and the field
    is empty" from "there is no such row" -- the first is a legitimate change
    target, the second is a client error worth a 422.
    """
    if field not in readable_columns(section):
        return False, None
    for row in rows:
        if section.is_repeating:
            if row.get("id") is not None and int(row["id"]) == record_id:
                return True, row.get(field)
        else:
            return True, row.get(field)
    return False, None
