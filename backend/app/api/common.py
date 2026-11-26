"""Helpers shared by the workspace routers."""

from __future__ import annotations

import uuid
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Membership

T = TypeVar("T")


def load(db: Session, model: type[T], workspace_id: uuid.UUID, obj_id: uuid.UUID, *, lock: bool = False) -> T:
    """Load a workspace-owned row by (workspace_id, id). Anything else is a 404."""
    stmt = select(model).where(model.workspace_id == workspace_id, model.id == obj_id)
    if lock:
        stmt = stmt.with_for_update()
    obj = db.scalar(stmt)
    if obj is None:
        raise HTTPException(404, "not_found")
    return obj


def require_member(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID | None, field: str) -> None:
    """People can only be assigned work in workspaces they belong to."""
    if user_id is None:
        return
    if db.get(Membership, (workspace_id, user_id)) is None:
        raise HTTPException(422, {"error": "validation_error", "fields": [{"loc": ["body", field], "msg": "not a member of this workspace"}]})

