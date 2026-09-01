"""Reading and writing Lapus change requests.

Every statement here targets `lapus.*`. Nothing in this module names a
parser-owned table except in read-only joins used to label a request with the
spec it belongs to.
"""

from __future__ import annotations

from typing import Any

from ..db.engine import Database, Row

_REQUEST_SUMMARY_SELECT = """
    SELECT
        r.request_id, r.document_id, r.title, r.reason, r.status,
        r.created_by, r.created_at, r.updated_at,
        r.submitted_by, r.submitted_at,
        r.decided_by, r.decided_at, r.decision_comment,
        d.filename, p.customer, p.spec_number, p.item,
        (SELECT COUNT(*) FROM lapus.change_item i WHERE i.request_id = r.request_id)
            AS item_count
    FROM lapus.change_request r
    LEFT JOIN t00_documents d ON d.id = r.document_id
    LEFT JOIN t01_product_description p ON p.document_id = r.document_id
"""

_ITEM_SELECT = """
    SELECT item_id, request_id, target_document_id, section_number, target_table,
           target_record_id, target_field, original_value, proposed_value,
           clears_value, change_comment, created_by, created_at, updated_at
    FROM lapus.change_item
"""


class ChangeRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    # -- requests --------------------------------------------------------------

    def create_request(self, document_id: int, title: str, reason: str | None,
                       actor: str) -> int:
        return self._db.insert_returning_id(
            """
            INSERT INTO lapus.change_request (document_id, title, reason, status, created_by)
            VALUES (?, ?, ?, 'DRAFT', ?)
            """,
            (document_id, title, reason, actor),
        )

    def get_request(self, request_id: int) -> Row | None:
        return self._db.query_one(
            f"{_REQUEST_SUMMARY_SELECT} WHERE r.request_id = ?", (request_id,)
        )

    def list_requests(self, status: str | None = None, document_id: int | None = None,
                      created_by: str | None = None, limit: int = 100) -> list[Row]:
        where: list[str] = []
        params: list[Any] = []
        if status:
            where.append("r.status = ?")
            params.append(status)
        if document_id is not None:
            where.append("r.document_id = ?")
            params.append(document_id)
        if created_by:
            where.append("r.created_by = ?")
            params.append(created_by)
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        params.append(max(1, min(limit, 500)))
        return self._db.query(
            f"{_REQUEST_SUMMARY_SELECT}{clause} ORDER BY r.updated_at DESC, r.request_id DESC "
            "LIMIT ?",
            params,
        )

    def update_request_status(self, request_id: int, status: str, actor: str,
                              comment: str | None = None) -> None:
        if status == "SUBMITTED":
            self._db.execute(
                """
                UPDATE lapus.change_request
                SET status = ?, submitted_by = ?, submitted_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE request_id = ?
                """,
                (status, actor, request_id),
            )
        elif status in {"APPROVED", "REJECTED"}:
            self._db.execute(
                """
                UPDATE lapus.change_request
                SET status = ?, decided_by = ?, decided_at = CURRENT_TIMESTAMP,
                    decision_comment = ?, updated_at = CURRENT_TIMESTAMP
                WHERE request_id = ?
                """,
                (status, actor, comment, request_id),
            )
        else:
            self._db.execute(
                """
                UPDATE lapus.change_request
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE request_id = ?
                """,
                (status, request_id),
            )

    def update_request_details(self, request_id: int, title: str, reason: str | None) -> None:
        self._db.execute(
            """
            UPDATE lapus.change_request
            SET title = ?, reason = ?, updated_at = CURRENT_TIMESTAMP
            WHERE request_id = ?
            """,
            (title, reason, request_id),
        )

    def delete_request(self, request_id: int) -> None:
        # Items and events cascade. Only ever reached for an empty DRAFT.
        self._db.execute("DELETE FROM lapus.change_request WHERE request_id = ?", (request_id,))

    # -- items ------------------------------------------------------------------

    def add_item(self, request_id: int, document_id: int, section_number: int,
                 target_table: str, target_record_id: int | None, target_field: str,
                 original_value: str | None, proposed_value: str | None,
                 clears_value: bool, comment: str | None, actor: str) -> int:
        return self._db.insert_returning_id(
            """
            INSERT INTO lapus.change_item
                (request_id, target_document_id, section_number, target_table,
                 target_record_id, target_field, original_value, proposed_value,
                 clears_value, change_comment, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (request_id, document_id, section_number, target_table, target_record_id,
             target_field, original_value, proposed_value, 1 if clears_value else 0,
             comment, actor),
        )

    def get_item(self, item_id: int) -> Row | None:
        return self._db.query_one(f"{_ITEM_SELECT} WHERE item_id = ?", (item_id,))

    def list_items(self, request_id: int) -> list[Row]:
        return self._db.query(
            f"{_ITEM_SELECT} WHERE request_id = ? ORDER BY section_number, item_id",
            (request_id,),
        )

    def find_duplicate_item(self, request_id: int, target_table: str,
                            target_record_id: int | None, target_field: str) -> Row | None:
        """Whether this request already proposes something for this exact field.

        NULL record ids need `IS NULL` rather than `= ?`, so the two cases are
        separate statements -- the same split the unique indexes make.
        """
        if target_record_id is None:
            return self._db.query_one(
                f"{_ITEM_SELECT} WHERE request_id = ? AND target_table = ? "
                "AND target_record_id IS NULL AND target_field = ?",
                (request_id, target_table, target_field),
            )
        return self._db.query_one(
            f"{_ITEM_SELECT} WHERE request_id = ? AND target_table = ? "
            "AND target_record_id = ? AND target_field = ?",
            (request_id, target_table, target_record_id, target_field),
        )

    def update_item(self, item_id: int, proposed_value: str | None, clears_value: bool,
                    comment: str | None) -> None:
        self._db.execute(
            """
            UPDATE lapus.change_item
            SET proposed_value = ?, clears_value = ?, change_comment = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE item_id = ?
            """,
            (proposed_value, 1 if clears_value else 0, comment, item_id),
        )

    def delete_item(self, item_id: int) -> None:
        self._db.execute("DELETE FROM lapus.change_item WHERE item_id = ?", (item_id,))

    # -- events -------------------------------------------------------------------

    def add_event(self, request_id: int, event_type: str, actor: str,
                  from_status: str | None = None, to_status: str | None = None,
                  comment: str | None = None) -> None:
        self._db.execute(
            """
            INSERT INTO lapus.change_event
                (request_id, event_type, from_status, to_status, event_comment, actor)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (request_id, event_type, from_status, to_status, comment, actor),
        )

    def list_events(self, request_id: int) -> list[Row]:
        return self._db.query(
            """
            SELECT event_id, request_id, event_type, from_status, to_status,
                   event_comment, actor, created_at
            FROM lapus.change_event
            WHERE request_id = ?
            ORDER BY created_at, event_id
            """,
            (request_id,),
        )

    # -- overlay and history --------------------------------------------------------

    def approved_items_for_document(self, document_id: int) -> list[Row]:
        """Every approved change item affecting one spec, oldest first.

        The overlay source. Ordered so that when two approved requests touched
        the same field, the later decision is applied last and therefore wins.
        """
        return self._db.query(
            """
            SELECT i.item_id, i.section_number, i.target_table, i.target_record_id,
                   i.target_field, i.original_value, i.proposed_value, i.clears_value,
                   i.change_comment, i.created_by, i.created_at,
                   r.request_id, r.title, r.decided_by, r.decided_at
            FROM lapus.change_item i
            JOIN lapus.change_request r ON r.request_id = i.request_id
            WHERE i.target_document_id = ? AND r.status = 'APPROVED'
            ORDER BY r.decided_at, r.request_id, i.item_id
            """,
            (document_id,),
        )

    def history_for_document(self, document_id: int) -> list[Row]:
        """Every Lapus change item ever raised against a spec, whatever its status.

        Distinct from t11_revision_history, which is the Word document's own
        revision record (AGENTS.md rule 8).
        """
        return self._db.query(
            """
            SELECT i.item_id, i.section_number, i.target_table, i.target_record_id,
                   i.target_field, i.original_value, i.proposed_value, i.clears_value,
                   i.change_comment, i.created_by, i.created_at,
                   r.request_id, r.title, r.status, r.submitted_by, r.submitted_at,
                   r.decided_by, r.decided_at, r.decision_comment
            FROM lapus.change_item i
            JOIN lapus.change_request r ON r.request_id = i.request_id
            WHERE i.target_document_id = ?
            ORDER BY r.created_at DESC, r.request_id DESC, i.section_number, i.item_id
            """,
            (document_id,),
        )

    def open_request_counts(self) -> Row:
        counts = self._db.query(
            "SELECT status, COUNT(*) AS n FROM lapus.change_request GROUP BY status"
        )
        return {row["status"]: row["n"] for row in counts}
