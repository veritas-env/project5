"""Synthetic demo data for HelpDesk Pro: two support teams with agents, tickets and notes.
Every name and address is invented. Used by `python -m app.cli seed-demo`."""

from __future__ import annotations

import random
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.security import hash_password
from .models import Activity, Membership, Ticket, TicketNote, User, Workspace

DOMAIN = "helpdesk.lab"
TEAMS = [
    ("Brightline Broadband Support", "Customer support for Brightline home broadband.", [
        ("rachel.adams", "Rachel Adams", "Support Lead", "owner"), ("scanner-a", "Chris Taylor", "Support Agent", "member"),
        ("imran.ali", "Imran Ali", "Team Lead", "manager"), ("beth.cole", "Beth Cole", "Support Agent", "member"),
        ("ken.wu", "Ken Wu", "QA Analyst", "viewer")],
     ["Internet keeps dropping in the evening", "Router lights flashing orange", "Can't log in to my account", "Speed much lower than advertised",
      "Moving house — transfer my service", "Bill higher than expected", "Wi-Fi doesn't reach upstairs", "Engineer didn't turn up",
      "Change of payment details", "Cancel my contract", "Static IP request", "Email setup on new phone"]),
    ("Kestrel Software Support", "Product support for the Kestrel invoicing app.", [
        ("scanner-b", "Morgan Reid", "Head of Support", "owner"), ("lena.fischer", "Lena Fischer", "Support Engineer", "member"),
        ("omar.haddad", "Omar Haddad", "Support Engineer", "member")],
     ["Invoice PDF shows wrong VAT", "Export to CSV missing columns", "Can't add a new user", "Recurring invoice didn't send",
      "Bank feed disconnected", "Password reset email not arriving", "Feature request: multi-currency", "App slow on large accounts"]),
]
FIRST = ["Olivia", "Noah", "Amelia", "Leo", "Isla", "Oscar", "Ava", "Arthur", "Mia", "Henry", "Freya", "Theo", "Grace", "Samir", "Hana"]
LAST = ["Hughes", "Patel", "Clarke", "Evans", "Okoye", "Murphy", "Nowak", "Bennett", "Kaur", "Fraser", "Lewis", "Rossi"]
NOTES = ["Asked the customer for their router model.", "Reproduced on our side.", "Escalated to second line.",
         "Customer confirmed the fix works.", "Waiting for engineering.", "Sent troubleshooting steps by email."]


def seed_demo(s: Session, upload_dir=None, seed: int = 2026) -> dict[str, str]:
    if s.scalar(select(Workspace.id).limit(1)) is not None:
        raise RuntimeError("database already has workspaces; reset it first")
    rnd = random.Random(seed)
    now = datetime.now(timezone.utc)
    passwords: dict[str, str] = {}

    def user(local, name, title, admin=False):
        pw = "Lab-" + secrets.token_urlsafe(18)
        u = User(email=f"{local}@{DOMAIN}", display_name=name, job_title=title, password_hash=hash_password(pw), is_platform_admin=admin)
        s.add(u)
        s.flush()
        passwords[u.email] = pw
        return u

    user("platform-admin", "Platform Administrator", "IT Security", admin=True)
    for name, desc, people, subjects in TEAMS:
        ws = Workspace(name=name, description=desc)
        s.add(ws)
        s.flush()
        agents = []
        for local, pname, title, role in people:
            u = user(local, pname, title)
            s.add(Membership(workspace_id=ws.id, user_id=u.id, role=role))
            if role != "viewer":
                agents.append(u)
        for n in range(40):
            first, last = rnd.choice(FIRST), rnd.choice(LAST)
            created = now - timedelta(days=rnd.uniform(0, 30), minutes=rnd.randint(0, 600))
            status = rnd.choice(["open", "open", "pending", "resolved", "resolved", "closed"])
            t = Ticket(workspace_id=ws.id, number=1001 + n, subject=rnd.choice(subjects),
                       description=f"Hi, {rnd.choice(subjects).lower()}. Can you help? Thanks, {first}",
                       requester_name=f"{first} {last}", requester_email=f"{first.lower()}.{last.lower()}{n}@example.com",
                       status=status, priority=rnd.choice(["low", "normal", "normal", "high", "urgent"]),
                       channel=rnd.choice(["email", "email", "phone", "chat", "web"]),
                       assignee_id=rnd.choice(agents).id if rnd.random() < 0.8 else None,
                       created_by=rnd.choice(agents).id, created_at=created, updated_at=created + timedelta(hours=rnd.randint(1, 48)))
            s.add(t)
            s.flush()
            for k in range(rnd.randint(0, 3)):
                s.add(TicketNote(ticket_id=t.id, author_id=rnd.choice(agents).id, body=rnd.choice(NOTES),
                                 created_at=created + timedelta(hours=k + 1)))
            s.add(Activity(workspace_id=ws.id, actor_id=t.created_by, verb="created", object_type="ticket", object_id=t.id,
                           summary=f"opened HD-{t.number} “{t.subject}”", at=created))
    s.commit()
    return passwords
