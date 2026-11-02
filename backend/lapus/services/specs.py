"""Assembling what the specification workspace shows.

Sits between the API routes and the repositories so route handlers stay thin
and the overlay rule is applied in exactly one place.
"""

from __future__ import annotations

from typing import Any

from ..catalog import load_sections, section_by_number
from ..db.engine import Database
from ..repositories.changes import ChangeRepository
from ..repositories.specs import SearchQuery, SpecRepository
from .overlay import build_field, index_approved_items, render_section


class SpecNotFound(RuntimeError):
    pass


class SpecService:
    def __init__(self, database: Database) -> None:
        self._specs = SpecRepository(database)
        self._changes = ChangeRepository(database)

    def search(self, query: SearchQuery) -> dict[str, Any]:
        rows, total = self._specs.search(query)
        return {
            "results": rows,
            "total": total,
            "limit": query.limit,
            "offset": query.offset,
            "has_more": query.offset + len(rows) < total,
        }

    def get_spec(self, document_id: int) -> dict[str, Any]:
        """Header, source metadata, parser status and section availability.

        Deliberately does not include section content: with eleven sections
        across a corpus this size, the workspace loads the header first and
        fetches a section when it is opened.
        """
        spec = self._specs.get_spec(document_id)
        if spec is None:
            raise SpecNotFound(f"No specification with document id {document_id}.")

        availability = self._specs.section_availability(document_id)
        approved = index_approved_items(self._changes.approved_items_for_document(document_id))
        overrides_by_section: dict[int, int] = {}
        for item in self._changes.approved_items_for_document(document_id):
            number = int(item["section_number"])
            overrides_by_section[number] = overrides_by_section.get(number, 0) + 1

        sections = [
            {
                "number": section.number,
                "key": section.key,
                "label": section.label,
                "layout": section.layout,
                "is_editable": section.is_editable,
                "row_count": availability.get(section.number, 0),
                "is_empty": availability.get(section.number, 0) == 0,
                "override_count": overrides_by_section.get(section.number, 0),
            }
            for section in load_sections()
        ]

        return {
            "document_id": document_id,
            "header": spec,
            "staging_status": self._specs.staging_status(document_id),
            "sections": sections,
            "approved_override_count": len(approved),
            "supplemental_table_count": len(self._specs.supplemental_tables(document_id)),
        }

    def get_section(self, document_id: int, section_number: int) -> dict[str, Any]:
        if not self._specs.document_exists(document_id):
            raise SpecNotFound(f"No specification with document id {document_id}.")
        section = section_by_number(section_number)
        rows = self._specs.section_rows(document_id, section)
        approved = index_approved_items(self._changes.approved_items_for_document(document_id))
        return render_section(section, rows, approved)

    def get_all_sections(self, document_id: int) -> list[dict[str, Any]]:
        """Every section at once, for printing or a single-page read."""
        if not self._specs.document_exists(document_id):
            raise SpecNotFound(f"No specification with document id {document_id}.")
        approved = index_approved_items(self._changes.approved_items_for_document(document_id))
        return [
            render_section(section, self._specs.section_rows(document_id, section), approved)
            for section in load_sections()
        ]

    def get_section_grid(self, section_number: int, query: SearchQuery) -> dict[str, Any]:
        """One section across every spec in scope, for bulk editing.

        Overlays are applied here exactly as they are for a single spec, so a
        value already carrying an approved change shows as such in the grid
        rather than looking like untouched source data.
        """
        section = section_by_number(section_number)
        rows, total = self._specs.section_grid(section, query)

        approved = index_approved_items(
            self._changes.approved_items_for_documents(
                sorted({int(row["document_id"]) for row in rows})
            )
        )

        fields = list(section.editable_fields)
        grid_rows: list[dict[str, Any]] = []
        for row in rows:
            record_id = int(row["id"]) if section.is_repeating and row.get("id") is not None else None
            grid_rows.append({
                "document_id": row["document_id"],
                "record_id": record_id,
                "filename": row.get("doc_filename"),
                "is_present": row.get("doc_is_present"),
                "customer": row.get("doc_customer"),
                "spec_number": row.get("doc_spec_number"),
                "item": row.get("doc_item"),
                "fields": {
                    field: build_field(row.get(field), approved.get((section.table, record_id, field)))
                    for field in fields
                },
            })

        return {
            "section": {
                "number": section.number,
                "key": section.key,
                "label": section.label,
                "table": section.table,
                "is_repeating": section.is_repeating,
                "is_editable": section.is_editable,
            },
            "fields": fields,
            "rows": grid_rows,
            "total": total,
            "limit": query.limit,
            "offset": query.offset,
            "has_more": query.offset + len(grid_rows) < total,
        }

    def get_change_history(self, document_id: int) -> dict[str, Any]:
        if not self._specs.document_exists(document_id):
            raise SpecNotFound(f"No specification with document id {document_id}.")
        return {
            "document_id": document_id,
            "items": self._changes.history_for_document(document_id),
            "requests": self._changes.list_requests(document_id=document_id),
        }

    def get_supplemental(self, document_id: int) -> list[dict[str, Any]]:
        return self._specs.supplemental_tables(document_id)
