"""Support tickets, internal notes and the team dashboard."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..models import ROLE_RANK, Activity, Ticket, TicketNote, User
from ..schemas import ActivityOut, DashboardOut, NoteIn, NoteOut, TicketIn, TicketOut, TicketStatus, TicketUpdate
from ..services import activity
from .common import load, require_member
from .deps import WorkspaceContext, workspace_access

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["tickets"])

COLUMNS = "id, number, subject, description, requester_name, requester_email, status, priority, channel, assignee_id, created_at, updated_at"


def ticket_out(t) -> TicketOut:
    return TicketOut(id=t.id, ref=f"HD-{t.number}", subject=t.subject, description=t.description, requester_name=t.requester_name,
                     requester_email=t.requester_email, status=t.status, priority=t.priority, channel=t.channel,
                     assignee_id=t.assignee_id, created_at=t.created_at, updated_at=t.updated_at)


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/tickets", response_model=list[TicketOut])
def list_tickets(
    ctx: WorkspaceContext = Depends(workspace_access("viewer")),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, max_length=100),
    status: TicketStatus | None = None,
    assignee: Literal["me", "none"] | None = None,
    sort: str = Query(default="updated_at", max_length=60),
    order: str = Query(default="desc", max_length=10),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[TicketOut]:
    where = ["workspace_id = :ws"]
    params: dict = {"ws": ctx.workspace.id, "limit": limit}
    if q:
        where.append("(subject ILIKE :q ESCAPE '\\' OR requester_email ILIKE :q ESCAPE '\\')")
        params["q"] = f"%{_escape_like(q)}%"
    if status:
        where.append("status = :status")
        params["status"] = status
    if assignee == "me":
        where.append("assignee_id = :me")
        params["me"] = ctx.user.id
    elif assignee == "none":
        where.append("assignee_id IS NULL")
    # Listing is read-only and must stay fast on large queues.
    db.execute(text("SET TRANSACTION READ ONLY"))
    db.execute(text("SET LOCAL statement_timeout = 2000"))
    sql = f"SELECT {COLUMNS} FROM tickets WHERE {' AND '.join(where)} ORDER BY {sort} {order}, number DESC LIMIT :limit"
    rows = db.execute(text(sql), params).all()
    db.rollback()
    return [ticket_out(r) for r in rows]


@router.post("/tickets", response_model=TicketOut, status_code=201)
def create_ticket(body: TicketIn, ctx: WorkspaceContext = Depends(workspace_access("member")), db: Session = Depends(get_db)) -> TicketOut:
    require_member(db, ctx.workspace.id, body.assignee_id, "assignee_id")
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(str(ctx.workspace.id)))))  # serialise numbering
    number = (db.scalar(select(func.max(Ticket.number)).where(Ticket.workspace_id == ctx.workspace.id)) or 1000) + 1
    t = Ticket(workspace_id=ctx.workspace.id, number=number, created_by=ctx.user.id, **body.model_dump())
    db.add(t)
    db.flush()
    activity.log(db, ctx.workspace.id, ctx.user.id, "created", "ticket", t.id, f"opened HD-{number} “{t.subject}”")
    db.commit()
    db.refresh(t)
    return ticket_out(t)


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_access("viewer")), db: Session = Depends(get_db)) -> TicketOut:
    return ticket_out(load(db, Ticket, ctx.workspace.id, ticket_id))


@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: uuid.UUID, body: TicketUpdate, ctx: WorkspaceContext = Depends(workspace_access("member")),
                  db: Session = Depends(get_db)) -> TicketOut:
    t = load(db, Ticket, ctx.workspace.id, ticket_id, lock=True)
    changes = body.model_dump(exclude_unset=True)
    if "assignee_id" in changes:
        require_member(db, ctx.workspace.id, changes["assignee_id"], "assignee_id")
    if changes.get("status") == "closed" and ROLE_RANK[ctx.role] < ROLE_RANK["manager"]:
        raise HTTPException(403, "forbidden")  # agents resolve; team leads close
    old = t.status
    for k, v in changes.items():
        setattr(t, k, v)
    if "status" in changes and changes["status"] != old:
        activity.log(db, ctx.workspace.id, ctx.user.id, "status", "ticket", t.id, f"moved HD-{t.number} from {old} to {t.status}")
    db.commit()
    db.refresh(t)
    return ticket_out(t)


@router.get("/tickets/{ticket_id}/notes", response_model=list[NoteOut])
def list_notes(ticket_id: uuid.UUID, ctx: WorkspaceContext = Depends(workspace_access("viewer")), db: Session = Depends(get_db)) -> list[NoteOut]:
    t = load(db, Ticket, ctx.workspace.id, ticket_id)
    rows = db.execute(select(TicketNote, User.display_name).outerjoin(User, User.id == TicketNote.author_id)
                      .where(TicketNote.ticket_id == t.id).order_by(TicketNote.id)).all()
    return [NoteOut(id=n.id, author_id=n.author_id, author_name=name, body=n.body, created_at=n.created_at) for n, name in rows]


@router.post("/tickets/{ticket_id}/notes", response_model=NoteOut, status_code=201)
def add_note(ticket_id: uuid.UUID, body: NoteIn, ctx: WorkspaceContext = Depends(workspace_access("member")),
             db: Session = Depends(get_db)) -> NoteOut:
    t = load(db, Ticket, ctx.workspace.id, ticket_id, lock=True)
    n = TicketNote(ticket_id=t.id, author_id=ctx.user.id, body=body.body)
    db.add(n)
    t.updated_at = func.now()
    activity.log(db, ctx.workspace.id, ctx.user.id, "noted", "ticket", t.id, f"added a note to HD-{t.number}")
    db.commit()
    db.refresh(n)
    return NoteOut(id=n.id, author_id=n.author_id, author_name=ctx.user.display_name, body=n.body, created_at=n.created_at)


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(ctx: WorkspaceContext = Depends(workspace_access("viewer")), db: Session = Depends(get_db)) -> DashboardOut:
    ws = ctx.workspace.id
    by_status = dict(db.execute(select(Ticket.status, func.count()).where(Ticket.workspace_id == ws).group_by(Ticket.status)).all())
    open_ = (Ticket.workspace_id == ws, Ticket.status.in_(("open", "pending")))
    recent = db.execute(select(Activity, User.display_name).outerjoin(User, User.id == Activity.actor_id)
                        .where(Activity.workspace_id == ws).order_by(Activity.id.desc()).limit(10)).all()
    return DashboardOut(
        by_status=by_status,
        unassigned_open=db.scalar(select(func.count()).select_from(Ticket).where(*open_, Ticket.assignee_id.is_(None))),
        mine_open=db.scalar(select(func.count()).select_from(Ticket).where(*open_, Ticket.assignee_id == ctx.user.id)),
        urgent_open=db.scalar(select(func.count()).select_from(Ticket).where(*open_, Ticket.priority == "urgent")),
        recent_activity=[ActivityOut(id=a.id, at=a.at, actor_name=name, summary=a.summary) for a, name in recent],
    )
