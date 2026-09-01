"""Specification read endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..catalog import UnknownTarget, load_sections
from ..db.engine import Database
from ..repositories.specs import SearchQuery
from ..services.specs import SpecNotFound, SpecService
from .deps import get_database

router = APIRouter(prefix="/api/specs", tags=["specifications"])


def _service(database: Annotated[Database, Depends(get_database)]) -> SpecService:
    return SpecService(database)


Service = Annotated[SpecService, Depends(_service)]


@router.get("")
def search_specs(
    service: Service,
    q: str | None = None,
    customer: str | None = None,
    spec_number: str | None = None,
    item: str | None = None,
    filename: str | None = None,
    structure: str | None = None,
    raw_material: str | None = None,
    include_missing: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return service.search(
        SearchQuery(
            text=q, customer=customer, spec_number=spec_number, item=item,
            filename=filename, structure=structure, raw_material=raw_material,
            include_missing=include_missing, limit=limit, offset=offset,
        )
    )


@router.get("/sections")
def list_sections() -> list[dict[str, Any]]:
    """The section contract itself, so the frontend renders from one source."""
    return [
        {
            "number": s.number, "key": s.key, "label": s.label, "layout": s.layout,
            "is_repeating": s.is_repeating, "is_editable": s.is_editable,
            "editable_fields": list(s.editable_fields),
        }
        for s in load_sections()
    ]


@router.get("/{document_id}")
def get_spec(document_id: int, service: Service) -> dict[str, Any]:
    try:
        return service.get_spec(document_id)
    except SpecNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{document_id}/sections")
def get_all_sections(document_id: int, service: Service) -> list[dict[str, Any]]:
    try:
        return service.get_all_sections(document_id)
    except SpecNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{document_id}/sections/{section_number}")
def get_section(document_id: int, section_number: int, service: Service) -> dict[str, Any]:
    try:
        return service.get_section(document_id, section_number)
    except SpecNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnknownTarget as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{document_id}/changes")
def get_change_history(document_id: int, service: Service) -> dict[str, Any]:
    try:
        return service.get_change_history(document_id)
    except SpecNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{document_id}/supplemental")
def get_supplemental(document_id: int, service: Service) -> list[dict[str, Any]]:
    """Parser content that belongs to no numbered section. Admin-facing."""
    return service.get_supplemental(document_id)
