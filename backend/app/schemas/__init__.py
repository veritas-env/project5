"""Request and response bodies. Every input is length- and format-bounded and
unknown fields are rejected."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,189}\.[A-Za-z]{2,24}$")

Role = Literal["viewer", "member", "manager", "owner"]
InviteRole = Literal["viewer", "member", "manager"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def normalize_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not _EMAIL_RE.match(v):
        raise ValueError("invalid email address")
    return v


# --- auth -----------------------------------------------------------------------

class LoginIn(StrictModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)


class PasswordChangeIn(StrictModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_platform_admin: bool


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


# --- workspaces, members, invitations ------------------------------------------

class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    role: str


class MemberOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    email: str
    job_title: str | None
    role: str
    joined_at: datetime


class RoleIn(StrictModel):
    role: Role


class InvitationIn(StrictModel):
    email: str = Field(max_length=254)
    role: InviteRole = "member"

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    created_at: datetime


class InvitationCreated(InvitationOut):
    invite_url: str  # shown once to the inviter; the token isn't stored in clear


class InvitationPreview(BaseModel):
    workspace_name: str
    email: str
    role: str
    account_exists: bool


class InvitationTokenIn(StrictModel):
    token: str = Field(min_length=20, max_length=100)


class InvitationRegisterIn(InvitationTokenIn):
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


# --- tickets ------------------------------------------------------------------------

TicketStatus = Literal["open", "pending", "resolved", "closed"]
TicketPriority = Literal["low", "normal", "high", "urgent"]
TicketChannel = Literal["email", "phone", "chat", "web"]


class TicketIn(StrictModel):
    subject: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    requester_name: str = Field(min_length=1, max_length=120)
    requester_email: str = Field(max_length=254)
    priority: TicketPriority = "normal"
    channel: TicketChannel = "email"
    assignee_id: uuid.UUID | None = None

    @field_validator("requester_email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)


class TicketUpdate(StrictModel):
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    assignee_id: uuid.UUID | None = None


class TicketOut(BaseModel):
    id: uuid.UUID
    ref: str
    subject: str
    description: str
    requester_name: str
    requester_email: str
    status: str
    priority: str
    channel: str
    assignee_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class NoteIn(StrictModel):
    body: str = Field(min_length=1, max_length=10_000)


class NoteOut(BaseModel):
    id: int
    author_id: uuid.UUID | None
    author_name: str | None
    body: str
    created_at: datetime


class ActivityOut(BaseModel):
    id: int
    at: datetime
    actor_name: str | None
    summary: str


class DashboardOut(BaseModel):
    by_status: dict[str, int]
    unassigned_open: int
    mine_open: int
    urgent_open: int
    recent_activity: list[ActivityOut]


# --- platform admin -------------------------------------------------------------

class EventOut(BaseModel):
    id: int
    at: datetime
    type: str
    severity: str
    actor_user_id: uuid.UUID | None
    workspace_id: uuid.UUID | None
    ip: str | None
    request_id: str | None
    detail: dict


class AlertOut(BaseModel):
    id: int
    at: datetime
    rule: str
    severity: str
    summary: str
    event_id: int | None
    status: str
