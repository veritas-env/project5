"""Business activity feed. Written in the same transaction as the change it describes,
so a rolled-back change leaves no activity entry behind."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from ..models import Activity


def log(db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID | None, verb: str, object_type: str,
        object_id: uuid.UUID | None, summary: str) -> None:
    db.add(Activity(workspace_id=workspace_id, actor_id=actor_id, verb=verb, object_type=object_type,
                    object_id=object_id, summary=summary[:300]))
