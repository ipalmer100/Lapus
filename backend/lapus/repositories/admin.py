"""Parser-health reads for the admin area (T00/V00 diagnostics).

Kept apart from SpecRepository because this is a different audience: normal
users read specifications and should never meet a mapping confidence score,
while whoever runs the parser needs exactly these numbers (AGENTS.md, UX rules).
"""

from __future__ import annotations

from ..db.engine import Database, Row


class AdminRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    def staging_summary(self) -> Row:
        """Corpus-level counts for the parser health panel."""
        documents = self._db.query_one(
            """
            SELECT COUNT(*) AS total_documents,
                   SUM(CASE WHEN is_present = 1 THEN 1 ELSE 0 END) AS present_documents,
                   SUM(CASE WHEN is_present = 0 THEN 1 ELSE 0 END) AS missing_documents,
                   COUNT(DISTINCT parser_version) AS parser_versions
            FROM t00_documents
            """
        ) or {}
        tables = self._db.query_one(
            """
            SELECT
                SUM(CASE WHEN status = 'mapped' THEN 1 ELSE 0 END) AS mapped_tables,
                SUM(CASE WHEN status = 'supplemental' THEN 1 ELSE 0 END) AS supplemental_tables,
                SUM(CASE WHEN status = 'unmapped' THEN 1 ELSE 0 END) AS unmapped_tables,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS error_tables
            FROM t00_ingestion_audit
            """
        ) or {}
        errors = self._db.scalar("SELECT COUNT(*) FROM t00_ingestion_errors") or 0
        versions = self._db.query(
            """
            SELECT parser_version, COUNT(*) AS document_count
            FROM t00_documents
            GROUP BY parser_version
            ORDER BY document_count DESC
            """
        )
        latest = self._db.query_one(
            "SELECT MAX(imported_at) AS last_import FROM t00_documents"
        ) or {}
        return {
            **documents,
            **tables,
            "ingestion_errors": errors,
            "parser_version_breakdown": versions,
            "last_import": latest.get("last_import"),
        }

    def documents_needing_attention(self, limit: int = 100) -> list[Row]:
        """Documents the parser could not fully place, worst first."""
        return self._db.query(
            """
            SELECT s.document_id, s.relative_path, s.filename, s.parser_version,
                   s.is_present, s.mapped_source_tables, s.supplemental_source_tables,
                   s.unmapped_source_tables, s.table_errors,
                   s.minimum_mapping_confidence
            FROM v00_document_staging_status s
            WHERE s.unmapped_source_tables > 0
               OR s.table_errors > 0
               OR s.supplemental_source_tables > 0
               OR s.is_present = 0
               OR s.minimum_mapping_confidence < 1.0
            ORDER BY s.table_errors DESC, s.unmapped_source_tables DESC,
                     s.minimum_mapping_confidence ASC, s.relative_path
            LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        )

    def exception_worklist(self, limit: int = 200) -> list[Row]:
        return self._db.query(
            """
            SELECT relative_path, source_table_index, detected_section, status,
                   mapping_method, mapping_confidence, details
            FROM v00_exception_worklist
            LIMIT ?
            """,
            (max(1, min(limit, 1000)),),
        )

    def ingestion_errors(self, limit: int = 100) -> list[Row]:
        """Documents that failed outright.

        Read separately rather than joined through t00_documents: a file that
        could not be parsed has no document row to join to.
        """
        return self._db.query(
            """
            SELECT id, relative_path, filename, error_type, error_message, created_at
            FROM t00_ingestion_errors
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        )

    def unmapped_tables(self, limit: int = 200) -> list[Row]:
        return self._db.query(
            """
            SELECT u.id, u.document_id, d.relative_path, u.source_table_index,
                   u.preceding_heading, u.signature, u.classification,
                   u.suggested_section, u.mapping_method
            FROM t00_unmapped_tables u
            JOIN t00_documents d ON d.id = u.document_id
            ORDER BY
                CASE WHEN u.classification = 'unmapped' THEN 0 ELSE 1 END,
                d.relative_path, u.source_table_index
            LIMIT ?
            """,
            (max(1, min(limit, 1000)),),
        )
