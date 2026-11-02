"""Change-request workflow rules."""

from __future__ import annotations

import pytest

from lapus.services.change_workflow import (
    Actor, ChangeWorkflow, NotFound, PermissionDenied, ValidationError, WorkflowError,
)
from lapus.services.specs import SpecService


@pytest.fixture
def draft(workflow: ChangeWorkflow, actor: Actor, first_document_id: int) -> int:
    request = workflow.create_request(actor, first_document_id, "Test request", "Because")
    return int(request["request_id"])


@pytest.fixture
def bom_record_id(database, first_document_id: int) -> int:
    section = SpecService(database).get_section(first_document_id, 3)
    return section["rows"][0]["record_id"]


def test_new_request_starts_as_draft_and_logs_an_event(workflow, actor, draft) -> None:
    request = workflow.get_request(actor, draft)
    assert request["status"] == "DRAFT"
    assert [e["event_type"] for e in request["events"]] == ["CREATED"]


def test_request_against_unknown_document_is_not_found(workflow, actor) -> None:
    with pytest.raises(NotFound):
        workflow.create_request(actor, 999_999, "Nope", None)


def test_request_needs_a_title(workflow, actor, first_document_id) -> None:
    with pytest.raises(ValidationError):
        workflow.create_request(actor, first_document_id, "   ", None)


def test_item_captures_the_current_value_when_proposed(workflow, actor, draft, bom_record_id, database, first_document_id) -> None:
    staged = SpecService(database).get_section(first_document_id, 3)["rows"][0]["fields"]["supplier"]["value"]
    item = workflow.add_item(actor, draft, 3, bom_record_id, "supplier", "Other Co", False, None)
    assert item["original_value"] == staged


def test_repeating_section_requires_a_row(workflow, actor, draft) -> None:
    with pytest.raises(ValidationError, match="which row"):
        workflow.add_item(actor, draft, 3, None, "supplier", "Other Co", False, None)


def test_single_record_section_rejects_a_row_id(workflow, actor, draft) -> None:
    with pytest.raises(ValidationError, match="one record"):
        workflow.add_item(actor, draft, 1, 12345, "customer", "Other Co", False, None)


def test_unknown_field_is_rejected(workflow, actor, draft, bom_record_id) -> None:
    with pytest.raises(ValidationError):
        workflow.add_item(actor, draft, 3, bom_record_id, "not_a_column", "x", False, None)


def test_revision_history_cannot_be_changed(workflow, actor, draft) -> None:
    """Section 11 is the source document's own history, not Lapus's to edit."""
    with pytest.raises(ValidationError):
        workflow.add_item(actor, draft, 11, 1, "revision", "rewritten", False, None)


def test_proposing_the_same_value_is_rejected(workflow, actor, draft, bom_record_id, database, first_document_id) -> None:
    staged = SpecService(database).get_section(first_document_id, 3)["rows"][0]["fields"]["supplier"]["value"]
    with pytest.raises(ValidationError, match="same as the current value"):
        workflow.add_item(actor, draft, 3, bom_record_id, "supplier", staged, False, None)


def test_a_change_needs_a_value_or_an_explicit_clear(workflow, actor, draft, bom_record_id) -> None:
    with pytest.raises(ValidationError, match="clearing the field"):
        workflow.add_item(actor, draft, 3, bom_record_id, "supplier", None, False, None)


def test_clearing_a_field_is_allowed_and_recorded(workflow, actor, draft, bom_record_id) -> None:
    item = workflow.add_item(actor, draft, 3, bom_record_id, "supplier", None, True, "No longer sourced")
    assert item["clears_value"] == 1
    assert item["proposed_value"] is None


def test_two_proposals_for_one_field_are_refused(workflow, actor, draft, bom_record_id) -> None:
    workflow.add_item(actor, draft, 3, bom_record_id, "supplier", "First Co", False, None)
    with pytest.raises(WorkflowError, match="already proposes"):
        workflow.add_item(actor, draft, 3, bom_record_id, "supplier", "Second Co", False, None)


def test_empty_request_cannot_be_submitted(workflow, actor, draft) -> None:
    with pytest.raises(WorkflowError, match="at least one change"):
        workflow.submit(actor, draft)


def test_submitted_request_is_frozen(workflow, actor, draft, bom_record_id) -> None:
    """Once submitted, items cannot change -- a reviewer approves what they read."""
    workflow.add_item(actor, draft, 3, bom_record_id, "supplier", "Other Co", False, None)
    workflow.submit(actor, draft)
    with pytest.raises(WorkflowError, match="can no longer be edited"):
        workflow.add_item(actor, draft, 3, bom_record_id, "caliper_mils", "0.5", False, None)


def test_only_the_author_can_edit_a_draft(workflow, actor, author, draft, bom_record_id) -> None:
    with pytest.raises(PermissionDenied):
        workflow.add_item(author, draft, 3, bom_record_id, "supplier", "Other Co", False, None)


def test_non_approver_cannot_decide(workflow, actor, author, draft, bom_record_id) -> None:
    workflow.add_item(actor, draft, 3, bom_record_id, "supplier", "Other Co", False, None)
    workflow.submit(actor, draft)
    with pytest.raises(PermissionDenied, match="not authorised"):
        workflow.approve(author, draft, None)


def test_separation_of_duties_when_self_approval_is_off(workflow, draft, bom_record_id) -> None:
    """With self-approval disabled, a submitter cannot decide their own request."""
    submitter = Actor(email="tester@example.com", is_approver=True, may_self_approve=False)
    workflow.add_item(submitter, draft, 3, bom_record_id, "supplier", "Other Co", False, None)
    workflow.submit(submitter, draft)
    with pytest.raises(PermissionDenied, match="someone other than"):
        workflow.approve(submitter, draft, None)


def test_rejection_requires_a_reason(workflow, actor, draft, bom_record_id) -> None:
    workflow.add_item(actor, draft, 3, bom_record_id, "supplier", "Other Co", False, None)
    workflow.submit(actor, draft)
    with pytest.raises(ValidationError, match="needs a reason"):
        workflow.reject(actor, draft, "  ")


def test_approved_request_cannot_be_decided_again(workflow, actor, draft, bom_record_id) -> None:
    workflow.add_item(actor, draft, 3, bom_record_id, "supplier", "Other Co", False, None)
    workflow.submit(actor, draft)
    workflow.approve(actor, draft, "Fine")
    with pytest.raises(WorkflowError):
        workflow.reject(actor, draft, "Changed my mind")


def test_draft_can_be_cancelled_and_then_is_closed(workflow, actor, draft) -> None:
    result = workflow.cancel(actor, draft, "Raised in error")
    assert result["status"] == "CANCELLED"
    with pytest.raises(WorkflowError):
        workflow.submit(actor, draft)


def test_every_transition_is_recorded(workflow, actor, draft, bom_record_id) -> None:
    workflow.add_item(actor, draft, 3, bom_record_id, "supplier", "Other Co", False, None)
    workflow.submit(actor, draft)
    result = workflow.approve(actor, draft, "Approved by QA")
    types = [e["event_type"] for e in result["events"]]
    assert types == ["CREATED", "ITEM_ADDED", "SUBMITTED", "APPROVED"]
    assert result["events"][-1]["from_status"] == "SUBMITTED"
    assert result["events"][-1]["to_status"] == "APPROVED"
    assert result["events"][-1]["event_comment"] == "Approved by QA"


def test_rejected_change_does_not_overlay(workflow, actor, draft, bom_record_id, database, first_document_id) -> None:
    """Only APPROVED items become an overlay. A rejection changes nothing."""
    specs = SpecService(database)
    before = specs.get_section(first_document_id, 3)["rows"][0]["fields"]["supplier"]
    workflow.add_item(actor, draft, 3, bom_record_id, "supplier", "Rejected Co", False, None)
    workflow.submit(actor, draft)
    workflow.reject(actor, draft, "Not qualified")
    after = specs.get_section(first_document_id, 3)["rows"][0]["fields"]["supplier"]
    assert after["value"] == before["value"]
    assert after["is_overridden"] is False


def test_later_approval_wins_for_the_same_field(workflow, actor, first_document_id, bom_record_id, database) -> None:
    """Two approved requests touching one field: the most recent decision shows."""
    specs = SpecService(database)
    for value in ("First Co", "Second Co"):
        request = workflow.create_request(actor, first_document_id, f"Change to {value}", None)
        rid = int(request["request_id"])
        workflow.add_item(actor, rid, 3, bom_record_id, "supplier", value, False, None)
        workflow.submit(actor, rid)
        workflow.approve(actor, rid, None)
    field = specs.get_section(first_document_id, 3)["rows"][0]["fields"]["supplier"]
    assert field["value"] == "Second Co"


# --- bulk editing ---------------------------------------------------------


def _grid_docs(database, limit: int = 6) -> list[int]:
    from lapus.repositories.specs import SearchQuery
    from lapus.services.specs import SpecService

    grid = SpecService(database).get_section_grid(7, SearchQuery(limit=limit))
    return [row["document_id"] for row in grid["rows"]]


def _proposal(document_id: int, value: str = "Required - 2 per core") -> dict:
    return {
        "document_id": document_id, "section_number": 7, "target_record_id": None,
        "target_field": "core_tags", "proposed_value": value,
        "clears_value": False, "change_comment": "Standardised",
    }


def test_bulk_edit_spans_many_specs_in_one_request(workflow, actor, database) -> None:
    """The case single-spec editing never exercised.

    target_record_id is NULL for a single-record section, so a duplicate guard
    keyed only on (request, table, field) treats the second spec as a repeat of
    the first -- which made a bulk edit fail on its second row.
    """
    documents = _grid_docs(database)
    assert len(documents) > 1
    request = workflow.create_request(actor, documents[0], "Bulk core tags", None)
    request_id = int(request["request_id"])

    result = workflow.add_items(actor, request_id, [_proposal(d) for d in documents])

    assert result["added"] == len(documents)
    detail = workflow.get_request(actor, request_id)
    assert {int(i["target_document_id"]) for i in detail["items"]} == set(documents)


def test_bulk_edit_still_refuses_a_real_duplicate(workflow, actor, database) -> None:
    """Two proposals for the same field of the same spec remain a conflict."""
    documents = _grid_docs(database, limit=3)
    request = workflow.create_request(actor, documents[0], "Bulk", None)
    request_id = int(request["request_id"])
    workflow.add_items(actor, request_id, [_proposal(d) for d in documents])

    with pytest.raises(WorkflowError, match="already proposes"):
        workflow.add_items(actor, request_id, [_proposal(documents[0], "Something else")])


def test_bulk_edit_is_all_or_nothing(workflow, actor, database) -> None:
    """One bad row rolls the whole batch back, and the message says which.

    A partial apply would leave someone reading a change request to work out
    which row silently did not take.
    """
    documents = _grid_docs(database, limit=4)
    request = workflow.create_request(actor, documents[0], "Bulk", None)
    request_id = int(request["request_id"])

    proposals = [_proposal(d) for d in documents]
    proposals[2]["target_field"] = "not_a_real_column"

    with pytest.raises(ValidationError, match="Change 3 of 4"):
        workflow.add_items(actor, request_id, proposals)

    assert workflow.get_request(actor, request_id)["items"] == []


def test_bulk_edit_captures_each_spec_own_staged_value(workflow, actor, database) -> None:
    """original_value is per spec, not copied from the first row."""
    from lapus.repositories.specs import SearchQuery
    from lapus.services.specs import SpecService

    grid = SpecService(database).get_section_grid(7, SearchQuery(limit=5))
    staged = {r["document_id"]: r["fields"]["slit_width"]["value"] for r in grid["rows"]}

    request = workflow.create_request(actor, next(iter(staged)), "Bulk widths", None)
    request_id = int(request["request_id"])
    workflow.add_items(actor, request_id, [
        {"document_id": d, "section_number": 7, "target_record_id": None,
         "target_field": "slit_width", "proposed_value": "99.000\"",
         "clears_value": False, "change_comment": None}
        for d in staged
    ])

    for item in workflow.get_request(actor, request_id)["items"]:
        assert item["original_value"] == staged[int(item["target_document_id"])]


def test_bulk_edit_enforces_the_allowlist(workflow, actor, database) -> None:
    """A grid edit cannot reach a field a single edit could not."""
    documents = _grid_docs(database, limit=2)
    request = workflow.create_request(actor, documents[0], "Bulk", None)
    request_id = int(request["request_id"])

    with pytest.raises(ValidationError):
        workflow.add_items(actor, request_id, [{
            "document_id": documents[0], "section_number": 11, "target_record_id": 1,
            "target_field": "revision", "proposed_value": "rewritten",
            "clears_value": False, "change_comment": None,
        }])


def test_bulk_edit_requires_a_draft(workflow, actor, database) -> None:
    documents = _grid_docs(database, limit=2)
    request = workflow.create_request(actor, documents[0], "Bulk", None)
    request_id = int(request["request_id"])
    workflow.add_items(actor, request_id, [_proposal(d) for d in documents])
    workflow.submit(actor, request_id)

    with pytest.raises(WorkflowError, match="no longer be edited"):
        workflow.add_items(actor, request_id, [_proposal(documents[0], "After submit")])


def test_bulk_edit_has_a_ceiling(workflow, actor, database) -> None:
    """A batch a reviewer could not read is not governance."""
    documents = _grid_docs(database, limit=2)
    request = workflow.create_request(actor, documents[0], "Bulk", None)
    request_id = int(request["request_id"])

    with pytest.raises(ValidationError, match="Split it into batches"):
        workflow.add_items(actor, request_id, [_proposal(documents[0])] * 501)
