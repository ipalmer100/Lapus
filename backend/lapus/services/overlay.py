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


def _field(value: Any, override: Row | None) -> dict[str, Any]:
    """Package one field value with its provenance."""
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


def index_approved_items(items: list[Row]) -> dict[tuple[str, int | None, str], Row]:
    """Key approved change items by the exact field they target.

    `items` arrives oldest-decision-first, so later approvals overwrite earlier
    ones for the same field and the most recent decision is what the user sees.
    """
    index: dict[tuple[str, int | None, str], Row] = {}
    for item in items:
        record_id = item.get("target_record_id")
        key = (
            item["target_table"],
            int(record_id) if record_id is not None else None,
            item["target_field"],
        )
        index[key] = item
    return index


def render_section(section: Section, rows: list[Row],
                   approved: dict[tuple[str, int | None, str], Row]) -> dict[str, Any]:
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
            override = approved.get((section.table, record_id, column))
            fields[column] = _field(value, override)

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
