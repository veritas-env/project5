"""Request dependencies: who is calling (A07), CSRF (A01), and what they may touch (A01).

Every route except the explicit public ones (see `PUBLIC_ROUTES` in tests) depends on
`current_user`, and every tenant route on `workspace_access(...)`. Tests enumerate the route
table to make sure nothing slips through."""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.sessions import CSRF_HEADER, SESSION_COOKIE, SessionData, SessionStore
from ..models import ROLE_RANK, Membership, Workspace, User
from ..services import audit

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def current_session(request: Request, store: SessionStore = Depends(get_store)) -> SessionData:
    sess = store.get(request.cookies.get(SESSION_COOKIE))
    if sess is None:
        raise HTTPException(401, "authentication_required")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sent, sess.csrf):
            audit.record(request, "csrf.rejected", actor=sess.user_id, severity="medium")
            raise HTTPException(403, "csrf_failed")
    request.state.session = sess
    return sess


def current_user(
    request: Request,
    sess: SessionData = Depends(current_session),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, uuid.UUID(sess.user_id))
    if user is None or not user.is_active:
        get_store(request).destroy_digest(sess.digest, sess.user_id)
        raise HTTPException(401, "authentication_required")
    return user


def platform_admin(request: Request, user: User = Depends(current_user)) -> User:
    if not user.is_platform_admin:
        audit.record(request, "authz.denied", actor=user.id, severity="medium", detail={"path": request.url.path, "need": "platform_admin"})
        raise HTTPException(404, "not_found")  # don't reveal that admin routes exist
    return user


@dataclass
class WorkspaceContext:
    workspace: Workspace
    user: User
    role: str


def workspace_access(min_role: str):
    """Dependency factory: caller must be a member of {workspace_id} with at least `min_role`.

    Non-members get 404 (the workspace's existence isn't revealed); members with too low a
    role get 403."""
    if min_role not in ROLE_RANK:
        raise ValueError(min_role)

    def dep(workspace_id: uuid.UUID, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> WorkspaceContext:
        row = db.execute(
            select(Workspace, Membership.role)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Workspace.id == workspace_id, Membership.user_id == user.id)
        ).first()
        if row is None:
            audit.record(request, "authz.denied", actor=user.id, workspace_id=workspace_id, severity="medium",
                         detail={"path": request.url.path, "reason": "not_member"})
            raise HTTPException(404, "not_found")
        workspace, role = row
        if ROLE_RANK[role] < ROLE_RANK[min_role]:
            audit.record(request, "authz.denied", actor=user.id, workspace_id=workspace_id, severity="medium",
                         detail={"path": request.url.path, "reason": "role", "have": role, "need": min_role})
            raise HTTPException(403, "forbidden")
        return WorkspaceContext(workspace, user, role)

    dep.min_role = min_role  # introspected by the route-coverage test
    return dep
