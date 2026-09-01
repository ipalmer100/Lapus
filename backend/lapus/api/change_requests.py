"""Change-request workflow endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..db.engine import Database
from ..services.change_workflow import (
    Actor,
    ChangeWorkflow,
    NotFound,
    PermissionDenied,
    ValidationError,
    WorkflowError,
)
from .deps import get_actor, get_database

router = APIRouter(prefix="/api/change-requests", tags=["change requests"])


def _workflow(database: Annotated[Database, Depends(get_database)]) -> ChangeWorkflow:
    return ChangeWorkflow(database)


Workflow = Annotated[ChangeWorkflow, Depends(_workflow)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


class CreateRequest(BaseModel):
    document_id: int
    title: str = Field(min_length=1, max_length=200)
    reason: str | None = None


class UpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    reason: str | None = None


class CreateItem(BaseModel):
    section_number: int = Field(ge=1, le=11)
    target_record_id: int | None = None
    target_field: str = Field(min_length=1, max_length=64)
    proposed_value: str | None = None
    # Distinguishes "propose an empty value" from "no value given" -- the UI
    # has to make an intentional clear explicit (PRODUCT_REQUIREMENTS.md).
    clears_value: bool = False
    change_comment: str | None = None


class UpdateItem(BaseModel):
    proposed_value: str | None = None
    clears_value: bool = False
    change_comment: str | None = None


class Decision(BaseModel):
    comment: str | None = None


def _handle(call):
    """Translate workflow errors into the documented status codes.

    Wrapped in one place so no route can accidentally leak an internal
    exception -- and so error text stays the human-readable message the service
    raised, never a database trace (API_CONTRACT.md, Response behavior).
    """
    try:
        return call()
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("")
def list_requests(
    workflow: Workflow,
    actor: CurrentActor,
    status: Annotated[str | None, Query()] = None,
    document_id: int | None = None,
    mine: bool = False,
) -> list[dict[str, Any]]:
    return _handle(
        lambda: workflow.list_requests(
            status=status, document_id=document_id,
            created_by=actor.email if mine else None,
        )
    )


@router.post("", status_code=201)
def create_request(body: CreateRequest, workflow: Workflow,
                   actor: CurrentActor) -> dict[str, Any]:
    return _handle(
        lambda: workflow.create_request(actor, body.document_id, body.title, body.reason)
    )


@router.get("/{request_id}")
def get_request(request_id: int, workflow: Workflow, actor: CurrentActor) -> dict[str, Any]:
    return _handle(lambda: workflow.get_request(actor, request_id))


@router.patch("/{request_id}")
def update_request(request_id: int, body: UpdateRequest, workflow: Workflow,
                   actor: CurrentActor) -> dict[str, Any]:
    return _handle(lambda: workflow.update_request(actor, request_id, body.title, body.reason))


@router.post("/{request_id}/items", status_code=201)
def add_item(request_id: int, body: CreateItem, workflow: Workflow,
             actor: CurrentActor) -> dict[str, Any]:
    return _handle(
        lambda: workflow.add_item(
            actor, request_id, body.section_number, body.target_record_id,
            body.target_field, body.proposed_value, body.clears_value,
            body.change_comment,
        )
    )


@router.patch("/{request_id}/items/{item_id}")
def update_item(request_id: int, item_id: int, body: UpdateItem, workflow: Workflow,
                actor: CurrentActor) -> dict[str, Any]:
    return _handle(
        lambda: workflow.update_item(
            actor, request_id, item_id, body.proposed_value, body.clears_value,
            body.change_comment,
        )
    )


@router.delete("/{request_id}/items/{item_id}", status_code=204)
def delete_item(request_id: int, item_id: int, workflow: Workflow,
                actor: CurrentActor) -> None:
    _handle(lambda: workflow.delete_item(actor, request_id, item_id))


@router.post("/{request_id}/submit")
def submit(request_id: int, workflow: Workflow, actor: CurrentActor) -> dict[str, Any]:
    return _handle(lambda: workflow.submit(actor, request_id))


@router.post("/{request_id}/approve")
def approve(request_id: int, body: Decision, workflow: Workflow,
            actor: CurrentActor) -> dict[str, Any]:
    return _handle(lambda: workflow.approve(actor, request_id, body.comment))


@router.post("/{request_id}/reject")
def reject(request_id: int, body: Decision, workflow: Workflow,
           actor: CurrentActor) -> dict[str, Any]:
    return _handle(lambda: workflow.reject(actor, request_id, body.comment))


@router.post("/{request_id}/cancel")
def cancel(request_id: int, body: Decision, workflow: Workflow,
           actor: CurrentActor) -> dict[str, Any]:
    return _handle(lambda: workflow.cancel(actor, request_id, body.comment))
