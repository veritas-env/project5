"""Workspace invitations.

- Managers invite viewers and members; only owners invite managers.
- The token is 256 bits, shown once to the inviter, stored only as a SHA-256 digest,
  single-use, valid for 7 days, and bound to the invited email address.
- Tokens travel in POST bodies, never in API URLs, so they don't end up in logs.
- Public endpoints (preview, register) are rate-limited per IP.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import hash_password, new_token, password_problems, token_digest
from ..core.sessions import SessionStore, hit_rate_limit
from ..models import ROLE_RANK, Invitation, Membership, User, Workspace
from ..schemas import (
    InvitationCreated,
    InvitationIn,
    InvitationOut,
    InvitationPreview,
    InvitationRegisterIn,
    InvitationTokenIn,
    SessionOut,
    WorkspaceOut,
)
from ..services import activity, audit
from .auth import _set_cookies, _user_out
from .deps import WorkspaceContext, current_user, get_store, workspace_access

router = APIRouter(tags=["invitations"])

VALID_FOR = timedelta(days=7)
PUBLIC_LIMIT = 20  # per IP per 5 minutes


def _out(i: Invitation) -> InvitationOut:
    return InvitationOut(id=i.id, email=i.email, role=i.role, expires_at=i.expires_at, created_at=i.created_at)


@router.get("/api/v1/workspaces/{workspace_id}/invitations", response_model=list[InvitationOut])
def pending(ctx: WorkspaceContext = Depends(workspace_access("manager")), db: Session = Depends(get_db)) -> list[InvitationOut]:
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(Invitation).where(
        Invitation.workspace_id == ctx.workspace.id, Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None), Invitation.expires_at > now).order_by(Invitation.created_at.desc()))
    return [_out(i) for i in rows]


@router.post("/api/v1/workspaces/{workspace_id}/invitations", response_model=InvitationCreated, status_code=201)
def invite(body: InvitationIn, request: Request, ctx: WorkspaceContext = Depends(workspace_access("manager")),
           db: Session = Depends(get_db)) -> InvitationCreated:
    if ROLE_RANK[body.role] >= ROLE_RANK["manager"] and ctx.role != "owner":
        raise HTTPException(403, "forbidden")
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing and db.get(Membership, (ctx.workspace.id, existing.id)):
        raise HTTPException(409, "already_member")
    now = datetime.now(timezone.utc)
    for old in db.scalars(select(Invitation).where(Invitation.workspace_id == ctx.workspace.id, Invitation.email == body.email,
                                                   Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None))):
        old.revoked_at = now
    token = new_token()
    inv = Invitation(workspace_id=ctx.workspace.id, email=body.email, role=body.role, token_digest=token_digest(token),
                     invited_by=ctx.user.id, expires_at=now + VALID_FOR)
    db.add(inv)
    db.flush()
    activity.log(db, ctx.workspace.id, ctx.user.id, "invited", "invitation", inv.id, f"invited {body.email} as {body.role}")
    db.commit()
    audit.record(request, "invitation.created", actor=ctx.user.id, workspace_id=ctx.workspace.id,
                 detail={"email": body.email, "role": body.role})
    return InvitationCreated(**_out(inv).model_dump(), invite_url=f"/invite#{token}")


@router.delete("/api/v1/workspaces/{workspace_id}/invitations/{invitation_id}", status_code=204)
def revoke(invitation_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_access("manager")),
           db: Session = Depends(get_db)) -> Response:
    inv = db.scalar(select(Invitation).where(Invitation.workspace_id == ctx.workspace.id, Invitation.id == invitation_id).with_for_update())
    if inv is None or inv.accepted_at or inv.revoked_at:
        raise HTTPException(404, "not_found")
    inv.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


def _valid(db: Session, request: Request, token: str, lock: bool = False) -> Invitation:
    stmt = select(Invitation).where(Invitation.token_digest == token_digest(token))
    if lock:
        stmt = stmt.with_for_update()
    inv = db.scalar(stmt)
    if inv is None or inv.accepted_at or inv.revoked_at or inv.expires_at <= datetime.now(timezone.utc):
        audit.record(request, "invitation.invalid", severity="low",
                     detail={"reason": "unknown" if inv is None else "used_revoked_or_expired"})
        raise HTTPException(404, "invitation_invalid")
    return inv


def _limit(request: Request, store: SessionStore) -> None:
    ip = audit.client_ip(request) or "unknown"
    if hit_rate_limit(store.r, f"invite:ip:{ip}", PUBLIC_LIMIT, 300):
        raise HTTPException(429, "too_many_requests", headers={"Retry-After": "300"})


@router.post("/api/v1/invitations/preview", response_model=InvitationPreview)
def preview(body: InvitationTokenIn, request: Request, db: Session = Depends(get_db),
            store: SessionStore = Depends(get_store)) -> InvitationPreview:
    _limit(request, store)
    inv = _valid(db, request, body.token)
    ws = db.get(Workspace, inv.workspace_id)
    exists = db.scalar(select(User.id).where(User.email == inv.email)) is not None
    return InvitationPreview(workspace_name=ws.name, email=inv.email, role=inv.role, account_exists=exists)


def _join(db: Session, inv: Invitation, user: User) -> Workspace:
    if db.get(Membership, (inv.workspace_id, user.id)) is None:
        db.add(Membership(workspace_id=inv.workspace_id, user_id=user.id, role=inv.role))
    inv.accepted_at = datetime.now(timezone.utc)
    activity.log(db, inv.workspace_id, user.id, "joined", "member", user.id, f"{user.display_name} joined as {inv.role}")
    return db.get(Workspace, inv.workspace_id)


@router.post("/api/v1/invitations/accept", response_model=WorkspaceOut)
def accept(body: InvitationTokenIn, request: Request, user: User = Depends(current_user),
           db: Session = Depends(get_db)) -> WorkspaceOut:
    inv = _valid(db, request, body.token, lock=True)
    if inv.email != user.email:
        audit.record(request, "invitation.email_mismatch", actor=user.id, workspace_id=inv.workspace_id, severity="medium")
        raise HTTPException(403, "invitation_for_other_email")
    ws = _join(db, inv, user)
    db.commit()
    audit.record(request, "invitation.accepted", actor=user.id, workspace_id=ws.id, detail={"role": inv.role})
    return WorkspaceOut(id=ws.id, name=ws.name, description=ws.description, role=inv.role)


@router.post("/api/v1/invitations/register", response_model=SessionOut, status_code=201)
def register(body: InvitationRegisterIn, request: Request, response: Response, db: Session = Depends(get_db),
             store: SessionStore = Depends(get_store)) -> SessionOut:
    _limit(request, store)
    inv = _valid(db, request, body.token, lock=True)
    if db.scalar(select(User.id).where(User.email == inv.email)) is not None:
        raise HTTPException(409, "account_exists")
    problems = password_problems(body.password, inv.email)
    if problems:
        raise HTTPException(422, {"error": "weak_password", "problems": problems})
    user = User(email=inv.email, display_name=body.display_name, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    _join(db, inv, user)
    db.commit()
    token, sess = store.create(str(user.id))
    _set_cookies(request, response, token, sess.csrf)
    audit.record(request, "account.created", actor=user.id, workspace_id=inv.workspace_id, detail={"via": "invitation"})
    audit.record(request, "auth.login_succeeded", actor=user.id, detail={"via": "registration"})
    return SessionOut(user=_user_out(user), csrf_token=sess.csrf)
