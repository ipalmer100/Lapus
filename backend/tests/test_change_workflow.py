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
