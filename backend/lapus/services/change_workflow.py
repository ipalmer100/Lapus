"""The change-request state machine and the rules around editing items.

Statuses and transitions (AGENTS.md, Change workflow):

    DRAFT ---submit---> SUBMITTED ---approve--> APPROVED
      |                     |      \--reject--> REJECTED
      \--cancel--> CANCELLED       \--cancel--> CANCELLED

Only DRAFT requests are editable, and only by their creator. Submission freezes
the items so a reviewer approves exactly what they read. Every transition writes
a lapus.change_event, which is append-only and is the audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..catalog import UnknownTarget, section_by_number, validate_target
from ..db.engine import Database, Row
from ..repositories.changes import ChangeRepository
from ..repositories.specs import SpecRepository
from ..services.overlay import current_value

DRAFT = "DRAFT"
SUBMITTED = "SUBMITTED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
CANCELLED = "CANCELLED"

# Transitions allowed from each status.
_ALLOWED: dict[str, set[str]] = {
    DRAFT: {SUBMITTED, CANCELLED},
    SUBMITTED: {APPROVED, REJECTED, CANCELLED},
    APPROVED: set(),
    REJECTED: set(),
    CANCELLED: set(),
}

# Statuses whose items may still be edited.
_EDITABLE_STATUSES = {DRAFT}


class WorkflowError(RuntimeError):
    """A workflow rule was broken. Maps to HTTP 409."""


class PermissionDenied(RuntimeError):
    """The current user may not do this. Maps to HTTP 403."""


class NotFound(RuntimeError):
    """Maps to HTTP 404."""


class ValidationError(RuntimeError):
    """Bad target or malformed input. Maps to HTTP 422."""


@dataclass(frozen=True)
class Actor:
    """Who is acting, and what they are allowed to do.

    A deliberately thin stand-in for real authentication: the POC runs as a
    single configured user (AGENTS.md, Security). Everything downstream takes
    identity from here rather than from the request body, so wiring in real
    identity later means changing how an Actor is constructed and nothing else.
    """

    email: str
    is_approver: bool = False
    # Separation of duties. Off means the submitter cannot also decide; the
    # single-user POC turns it on so the approval step is reachable at all
    # (see Settings.allow_self_approval).
    may_self_approve: bool = False


class ChangeWorkflow:
    def __init__(self, database: Database) -> None:
        self._db = database
        self._changes = ChangeRepository(database)
        self._specs = SpecRepository(database)

    # -- requests ----------------------------------------------------------------

    def create_request(self, actor: Actor, document_id: int, title: str,
                       reason: str | None) -> Row:
        if not self._specs.document_exists(document_id):
            raise NotFound(f"No specification with document id {document_id}.")
        title = (title or "").strip()
        if not title:
            raise ValidationError("A change request needs a title.")

        with self._db.transaction():
            request_id = self._changes.create_request(document_id, title, reason, actor.email)
            self._changes.add_event(
                request_id, "CREATED", actor.email, to_status=DRAFT,
                comment=reason,
            )
        return self.get_request(actor, request_id)

    def get_request(self, actor: Actor, request_id: int) -> Row:
        request = self._changes.get_request(request_id)
        if request is None:
            raise NotFound(f"No change request {request_id}.")
        return {
            **request,
            "items": self._changes.list_items(request_id),
            "events": self._changes.list_events(request_id),
            "can_edit": self._can_edit(actor, request),
            "can_submit": self._can_edit(actor, request)
                          and bool(self._changes.list_items(request_id)),
            "can_decide": request["status"] == SUBMITTED and actor.is_approver,
        }

    def list_requests(self, status: str | None = None, document_id: int | None = None,
                      created_by: str | None = None) -> list[Row]:
        if status and status not in _ALLOWED:
            raise ValidationError(f"'{status}' is not a change request status.")
        return self._changes.list_requests(status, document_id, created_by)

    def update_request(self, actor: Actor, request_id: int, title: str,
                       reason: str | None) -> Row:
        request = self._require_editable(actor, request_id)
        title = (title or "").strip()
        if not title:
            raise ValidationError("A change request needs a title.")
        with self._db.transaction():
            self._changes.update_request_details(request["request_id"], title, reason)
        return self.get_request(actor, request_id)

    # -- items ---------------------------------------------------------------------

    def add_item(self, actor: Actor, request_id: int, section_number: int,
                 target_record_id: int | None, target_field: str,
                 proposed_value: str | None, clears_value: bool,
                 comment: str | None) -> Row:
        """Attach one field-level proposal to a draft request.

        The staged value is read here and stored on the item, rather than being
        looked up when the request is later reviewed: `original_value` must be
        what the field held at the moment the change was proposed, so a reviewer
        can see whether the source has moved underneath them.
        """
        request = self._require_editable(actor, request_id)
        document_id = int(request["document_id"])

        section = section_by_number(section_number)
        try:
            validate_target(section.table, target_field)
        except UnknownTarget as exc:
            raise ValidationError(str(exc)) from exc

        if section.is_repeating and target_record_id is None:
            raise ValidationError(
                f"{section.label} has many rows, so a change must name which row to alter."
            )
        if not section.is_repeating and target_record_id is not None:
            # One row per document: a record id would be meaningless and would
            # break overlay matching, which keys single-record sections on None.
            raise ValidationError(f"{section.label} holds one record per specification.")

        rows = self._specs.section_rows(document_id, section)
        found, original = current_value(rows, section, target_record_id, target_field)
        if not found:
            raise ValidationError(
                "That row is no longer in the staged specification. "
                "Reload the specification and try again."
            )

        proposed_value = None if clears_value else proposed_value
        if not clears_value and proposed_value is None:
            raise ValidationError(
                "Give a proposed value, or mark the change as clearing the field."
            )
        if not clears_value and str(proposed_value) == ("" if original is None else str(original)):
            raise ValidationError("The proposed value is the same as the current value.")

        duplicate = self._changes.find_duplicate_item(
            request_id, section.table, target_record_id, target_field
        )
        if duplicate is not None:
            raise WorkflowError(
                "This request already proposes a change to that field. "
                "Edit the existing item instead."
            )

        with self._db.transaction():
            item_id = self._changes.add_item(
                request_id, document_id, section.number, section.table, target_record_id,
                target_field, None if original is None else str(original),
                proposed_value, clears_value, comment, actor.email,
            )
            self._changes.add_event(
                request_id, "ITEM_ADDED", actor.email,
                comment=f"{section.label}: {target_field}",
            )
            self._changes.update_request_status(request_id, DRAFT, actor.email)
        item = self._changes.get_item(item_id)
        if item is None:  # pragma: no cover - the insert just succeeded
            raise NotFound("The change item could not be read back.")
        return item

    def update_item(self, actor: Actor, request_id: int, item_id: int,
                    proposed_value: str | None, clears_value: bool,
                    comment: str | None) -> Row:
        self._require_editable(actor, request_id)
        item = self._changes.get_item(item_id)
        if item is None or int(item["request_id"]) != request_id:
            raise NotFound(f"No change item {item_id} on request {request_id}.")

        proposed_value = None if clears_value else proposed_value
        if not clears_value and proposed_value is None:
            raise ValidationError(
                "Give a proposed value, or mark the change as clearing the field."
            )

        with self._db.transaction():
            self._changes.update_item(item_id, proposed_value, clears_value, comment)
            self._changes.add_event(
                request_id, "ITEM_UPDATED", actor.email,
                comment=f"{item['target_table']}: {item['target_field']}",
            )
        updated = self._changes.get_item(item_id)
        if updated is None:  # pragma: no cover
            raise NotFound("The change item could not be read back.")
        return updated

    def delete_item(self, actor: Actor, request_id: int, item_id: int) -> None:
        self._require_editable(actor, request_id)
        item = self._changes.get_item(item_id)
        if item is None or int(item["request_id"]) != request_id:
            raise NotFound(f"No change item {item_id} on request {request_id}.")
        with self._db.transaction():
            self._changes.delete_item(item_id)
            self._changes.add_event(
                request_id, "ITEM_REMOVED", actor.email,
                comment=f"{item['target_table']}: {item['target_field']}",
            )

    # -- transitions -------------------------------------------------------------------

    def submit(self, actor: Actor, request_id: int) -> Row:
        request = self._require_editable(actor, request_id)
        if not self._changes.list_items(request_id):
            raise WorkflowError("A change request needs at least one change before it is submitted.")
        return self._transition(actor, request, SUBMITTED, "SUBMITTED", None)

    def approve(self, actor: Actor, request_id: int, comment: str | None) -> Row:
        request = self._require_status(request_id, SUBMITTED)
        self._require_approver(actor, request)
        return self._transition(actor, request, APPROVED, "APPROVED", comment)

    def reject(self, actor: Actor, request_id: int, comment: str | None) -> Row:
        request = self._require_status(request_id, SUBMITTED)
        self._require_approver(actor, request)
        if not (comment or "").strip():
            raise ValidationError("A rejection needs a reason.")
        return self._transition(actor, request, REJECTED, "REJECTED", comment)

    def cancel(self, actor: Actor, request_id: int, comment: str | None) -> Row:
        request = self._changes.get_request(request_id)
        if request is None:
            raise NotFound(f"No change request {request_id}.")
        if request["created_by"] != actor.email and not actor.is_approver:
            raise PermissionDenied("Only the author or an approver can cancel a change request.")
        return self._transition(actor, request, CANCELLED, "CANCELLED", comment)

    def _transition(self, actor: Actor, request: Row, to_status: str,
                    event_type: str, comment: str | None) -> Row:
        from_status = request["status"]
        request_id = int(request["request_id"])
        if to_status not in _ALLOWED.get(from_status, set()):
            raise WorkflowError(
                f"A {from_status.lower()} change request cannot be moved to {to_status.lower()}."
            )
        with self._db.transaction():
            self._changes.update_request_status(request_id, to_status, actor.email, comment)
            self._changes.add_event(
                request_id, event_type, actor.email,
                from_status=from_status, to_status=to_status, comment=comment,
            )
        return self.get_request(actor, request_id)

    # -- guards -------------------------------------------------------------------------

    def _can_edit(self, actor: Actor, request: Row) -> bool:
        return (
            request["status"] in _EDITABLE_STATUSES
            and request["created_by"] == actor.email
        )

    def _require_editable(self, actor: Actor, request_id: int) -> Row:
        request = self._changes.get_request(request_id)
        if request is None:
            raise NotFound(f"No change request {request_id}.")
        if request["status"] not in _EDITABLE_STATUSES:
            raise WorkflowError(
                f"This change request is {request['status'].lower()} and can no longer be edited."
            )
        if request["created_by"] != actor.email:
            raise PermissionDenied("Only the author of a draft change request can edit it.")
        return request

    def _require_status(self, request_id: int, status: str) -> Row:
        request = self._changes.get_request(request_id)
        if request is None:
            raise NotFound(f"No change request {request_id}.")
        if request["status"] != status:
            raise WorkflowError(
                f"This change request is {request['status'].lower()}, not {status.lower()}."
            )
        return request

    def _require_approver(self, actor: Actor, request: Row) -> None:
        if not actor.is_approver:
            raise PermissionDenied("You are not authorised to approve or reject change requests.")
        if request["submitted_by"] == actor.email and not actor.may_self_approve:
            # Separation of duties: whoever submitted a request cannot also be
            # the one who approves it.
            raise PermissionDenied(
                "A change request must be reviewed by someone other than the person who submitted it."
            )
