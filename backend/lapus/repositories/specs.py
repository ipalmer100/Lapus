"""Reading specifications out of the parser-owned staging tables.

Everything here is SELECT-only by construction: on SQLite the staging database
is attached read-only, so these queries could not write even if one were
malformed.

Search runs entirely in the database. The corpus is ~14,000 documents with tens
of thousands of material rows behind them, so the browser is sent matching
specs, never rows to filter itself (CODEX_START_PROMPT.md, "Search behavior").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..catalog import Section, load_sections, readable_columns, section_by_number
from ..db.engine import Database, Row

# The spec-list projection, shared by search and detail so a result row and a
# workspace header cannot disagree about what a spec is called.
_SPEC_LIST_SELECT = """
    SELECT
        d.id                     AS document_id,
        d.filename               AS filename,
        d.relative_path          AS relative_path,
        d.source_directory       AS source_directory,
        d.imported_at            AS imported_at,
        d.last_seen_at           AS last_seen_at,
        d.parser_version         AS parser_version,
        d.is_present             AS is_present,
        p.customer               AS customer,
        p.spec_number            AS spec_number,
        p.item                   AS item,
        p.date_of_issue          AS date_of_issue,
        p.structure_description  AS structure_description,
        p.revision_number        AS revision_number,
        p.structure_code         AS structure_code
    FROM t00_documents d
    LEFT JOIN t01_product_description p ON p.document_id = d.id
"""


@dataclass(frozen=True)
class SearchQuery:
    """One search request. Every field is optional; all supplied ones must match."""

    text: str | None = None
    customer: str | None = None
    spec_number: str | None = None
    item: str | None = None
    filename: str | None = None
    structure: str | None = None
    raw_material: str | None = None
    include_missing: bool = False
    limit: int = 50
    offset: int = 0


class SpecRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    # -- search ---------------------------------------------------------------

    def search(self, query: SearchQuery) -> tuple[list[Row], int]:
        """Return one page of matching specs and the total match count."""
        where, params = self._search_predicates(query)
        clause = f" WHERE {' AND '.join(where)}" if where else ""

        total = self._db.scalar(
            f"SELECT COUNT(*) FROM t00_documents d "
            f"LEFT JOIN t01_product_description p ON p.document_id = d.id{clause}",
            params,
        )

        # Sorted so results are stable across pages: an unordered LIMIT/OFFSET
        # can repeat or skip rows between requests.
        rows = self._db.query(
            f"{_SPEC_LIST_SELECT}{clause} "
            "ORDER BY p.customer, p.spec_number, d.filename, d.id "
            "LIMIT ? OFFSET ?",
            [*params, max(1, min(query.limit, 200)), max(0, query.offset)],
        )
        return rows, int(total or 0)

    def _search_predicates(self, query: SearchQuery) -> tuple[list[str], list[Any]]:
        like = self._db.dialect.ilike_operator
        where: list[str] = []
        params: list[Any] = []

        if not query.include_missing:
            # Documents whose source file has disappeared stay staged, but are
            # out of the way unless explicitly asked for.
            where.append("d.is_present = 1")

        def contains(column: str, value: str | None) -> None:
            if value and value.strip():
                where.append(f"{column} {like} ?")
                params.append(f"%{value.strip()}%")

        contains("p.customer", query.customer)
        contains("p.spec_number", query.spec_number)
        contains("p.item", query.item)
        contains("d.filename", query.filename)
        contains("p.structure_description", query.structure)

        if query.text and query.text.strip():
            # The single search box: one term tried against every identifier a
            # user is likely to have to hand, including material data in the
            # child tables. The EXISTS subqueries keep that in the database
            # rather than pulling material rows back to compare here.
            term = f"%{query.text.strip()}%"
            columns = [
                "p.customer", "p.spec_number", "p.item", "d.filename",
                "p.structure_description", "p.structure_code", "d.relative_path",
            ]
            fragments = [f"{column} {like} ?" for column in columns]
            params.extend([term] * len(columns))
            for table in ("t03_bill_of_materials", "t04_secondary_approved_materials"):
                fragments.append(
                    f"EXISTS (SELECT 1 FROM {table} m WHERE m.document_id = d.id "
                    f"AND (m.raw_material {like} ? OR m.supplier {like} ? "
                    f"OR m.raw_material_item_code {like} ?))"
                )
                params.extend([term, term, term])
            where.append(f"({' OR '.join(fragments)})")

        if query.raw_material and query.raw_material.strip():
            # A dedicated material filter, deliberately narrower than the free
            # text box: "which specs use this web?" is its own question.
            term = f"%{query.raw_material.strip()}%"
            fragments = []
            for table in ("t03_bill_of_materials", "t04_secondary_approved_materials"):
                fragments.append(
                    f"EXISTS (SELECT 1 FROM {table} m WHERE m.document_id = d.id "
                    f"AND (m.raw_material {like} ? OR m.supplier {like} ? "
                    f"OR m.raw_material_item_code {like} ?))"
                )
                params.extend([term, term, term])
            where.append(f"({' OR '.join(fragments)})")

        return where, params

    # -- one specification ------------------------------------------------------

    def get_spec(self, document_id: int) -> Row | None:
        return self._db.query_one(
            f"{_SPEC_LIST_SELECT} WHERE d.id = ?", (document_id,)
        )

    def staging_status(self, document_id: int) -> Row | None:
        """Parser health for one document, from the V00 QA view."""
        return self._db.query_one(
            """
            SELECT document_id, relative_path, filename, parser_version, is_present,
                   mapped_source_tables, supplemental_source_tables,
                   unmapped_source_tables, table_errors, minimum_mapping_confidence
            FROM v00_document_staging_status
            WHERE document_id = ?
            """,
            (document_id,),
        )

    def section_availability(self, document_id: int) -> dict[int, int]:
        """How many staged rows each section holds for this document.

        Lets the workspace grey out sections that genuinely have no content
        instead of making the user click into eleven of them to find out --
        and a zero here is a valid state, not an error (AGENTS.md rule 7).
        """
        counts: dict[int, int] = {}
        for section in load_sections():
            # section.table comes from the allowlist, never from user input.
            counts[section.number] = int(
                self._db.scalar(
                    f"SELECT COUNT(*) FROM {section.table} WHERE document_id = ?",
                    (document_id,),
                )
                or 0
            )
        return counts

    def section_rows(self, document_id: int, section: Section) -> list[Row]:
        """Raw staged rows for one section, in source-document order."""
        columns = ", ".join(readable_columns(section))
        order = "source_row, id" if section.is_repeating else "document_id"
        return self._db.query(
            f"SELECT {columns} FROM {section.table} WHERE document_id = ? ORDER BY {order}",
            (document_id,),
        )

    def section_rows_by_number(self, document_id: int, number: int) -> list[Row]:
        return self.section_rows(document_id, section_by_number(number))

    def document_exists(self, document_id: int) -> bool:
        return bool(
            self._db.scalar("SELECT COUNT(*) FROM t00_documents WHERE id = ?", (document_id,))
        )

    def supplemental_tables(self, document_id: int) -> list[Row]:
        """Parser content that belongs to no numbered section (T00 diagnostics)."""
        return self._db.query(
            """
            SELECT id, source_table_index, preceding_heading, signature,
                   classification, suggested_section, mapping_method, raw_json
            FROM t00_unmapped_tables
            WHERE document_id = ?
            ORDER BY source_table_index
            """,
            (document_id,),
        )
