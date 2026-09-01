"""Parser-health endpoints. Admin-only: normal users never need these."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from ..db.engine import Database
from ..repositories.admin import AdminRepository
from ..repositories.changes import ChangeRepository
from ..services.change_workflow import Actor
from .deps import get_database, require_approver

router = APIRouter(prefix="/api/admin", tags=["admin"])

Db = Annotated[Database, Depends(get_database)]
Approver = Annotated[Actor, Depends(require_approver)]


@router.get("/staging-status")
def staging_status(database: Db, actor: Approver) -> dict[str, Any]:
    admin = AdminRepository(database)
    return {
        "summary": admin.staging_summary(),
        "needs_attention": admin.documents_needing_attention(),
        "change_request_counts": ChangeRepository(database).open_request_counts(),
    }


@router.get("/exceptions")
def exceptions(
    database: Db,
    actor: Approver,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict[str, Any]:
    admin = AdminRepository(database)
    return {
        "worklist": admin.exception_worklist(limit),
        "unmapped_tables": admin.unmapped_tables(limit),
        "ingestion_errors": admin.ingestion_errors(limit),
    }
