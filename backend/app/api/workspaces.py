"""Workspaces and their members."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import ROLE_RANK, Membership, Ticket, User, Workspace
from ..schemas import MemberOut, RoleIn, WorkspaceOut
from ..services import activity, audit
from .deps import WorkspaceContext, current_user, workspace_access

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceOut])
def my_workspaces(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[WorkspaceOut]:
    rows = db.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user.id)
        .order_by(Workspace.name)
    ).all()
    return [WorkspaceOut(id=w.id, name=w.name, description=w.description, role=r) for w, r in rows]


@router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(ctx: WorkspaceContext = Depends(workspace_access("viewer"))) -> WorkspaceOut:
    w = ctx.workspace
    return WorkspaceOut(id=w.id, name=w.name, description=w.description, role=ctx.role)


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
def members(ctx: WorkspaceContext = Depends(workspace_access("viewer")), db: Session = Depends(get_db)) -> list[MemberOut]:
    rows = db.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.workspace_id == ctx.workspace.id)
        .order_by(User.display_name)
    ).all()
    return [MemberOut(user_id=u.id, display_name=u.display_name, email=u.email, job_title=u.job_title,
                      role=m.role, joined_at=m.created_at) for u, m in rows]


def _owners(db: Session, workspace_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(Membership).where(
        Membership.workspace_id == workspace_id, Membership.role == "owner"))


@router.put("/{workspace_id}/members/{user_id}", response_model=MemberOut)
def set_role(user_id: uuid.UUID, body: RoleIn, request: Request,
             ctx: WorkspaceContext = Depends(workspace_access("owner")), db: Session = Depends(get_db)) -> MemberOut:
    m = db.scalar(select(Membership).where(Membership.workspace_id == ctx.workspace.id,
                                           Membership.user_id == user_id).with_for_update())
    if m is None:
        raise HTTPException(404, "not_found")
    if m.role == "owner" and body.role != "owner" and _owners(db, ctx.workspace.id) <= 1:
        raise HTTPException(409, "last_owner")
    old = m.role
    m.role = body.role
    target = db.get(User, user_id)
    activity.log(db, ctx.workspace.id, ctx.user.id, "changed_role", "member", user_id,
                 f"changed {target.display_name}'s role from {old} to {body.role}")
    db.commit()
    elevated = ROLE_RANK[body.role] > ROLE_RANK[old] and ROLE_RANK[body.role] >= ROLE_RANK["manager"]
    audit.record(request, "membership.role_elevated" if elevated else "membership.role_changed",
                 actor=ctx.user.id, workspace_id=ctx.workspace.id, severity="high" if elevated else "info",
                 detail={"target": str(user_id), "from": old, "to": body.role})
    return MemberOut(user_id=target.id, display_name=target.display_name, email=target.email,
                     job_title=target.job_title, role=m.role, joined_at=m.created_at)


@router.delete("/{workspace_id}/members/{user_id}", status_code=204)
def remove_member(user_id: uuid.UUID, request: Request,
                  ctx: WorkspaceContext = Depends(workspace_access("manager")), db: Session = Depends(get_db)) -> Response:
    m = db.scalar(select(Membership).where(Membership.workspace_id == ctx.workspace.id,
                                           Membership.user_id == user_id).with_for_update())
    if m is None:
        raise HTTPException(404, "not_found")
    # Managers may remove members and viewers; only owners may remove managers or owners.
    if ROLE_RANK[m.role] >= ROLE_RANK["manager"] and ctx.role != "owner":
        raise HTTPException(403, "forbidden")
    if m.role == "owner" and _owners(db, ctx.workspace.id) <= 1:
        raise HTTPException(409, "last_owner")
    target = db.get(User, user_id)
    db.delete(m)
    # Their tickets in this workspace go back to the unassigned queue.
    for t in db.scalars(select(Ticket).where(Ticket.workspace_id == ctx.workspace.id, Ticket.assignee_id == user_id)):
        t.assignee_id = None
    activity.log(db, ctx.workspace.id, ctx.user.id, "removed", "member", user_id, f"removed {target.display_name} from the workspace")
    db.commit()
    audit.record(request, "membership.removed", actor=ctx.user.id, workspace_id=ctx.workspace.id,
                 detail={"target": str(user_id), "role": m.role})
    return Response(status_code=204)
