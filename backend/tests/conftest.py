"""Shared fixtures.

Database: APP_TEST_DATABASE_URL if set (CI uses a Postgres service), otherwise a
throwaway local cluster (tests/pgtemp.py). Redis: fakeredis.

`world` seeds two workspaces:
    Workspace A: alice (owner), adam (manager), bob (member), vera (viewer)
                 ticket A (with a note), a pending invitation
    Workspace B: mallory (owner), ticket B
    root: platform admin, member of nothing
"""

from __future__ import annotations

import os
import secrets
import uuid
from dataclasses import dataclass, field

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.pgtemp import TempPostgres

TABLES = ["alerts", "security_events", "activity", "ticket_notes", "tickets", "invitations", "memberships",
          "workspaces", "users"]


@pytest.fixture(scope="session")
def pg_url():
    url = os.environ.get("APP_TEST_DATABASE_URL")
    pg = None
    if not url:
        pg = TempPostgres()
        url = pg.start()
    from alembic import command
    from alembic.config import Config

    here = os.path.dirname(__file__)
    cfg = Config(os.path.join(here, "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "..", "migrations"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    yield url
    if pg:
        pg.stop()


@pytest.fixture
def settings(pg_url, tmp_path):
    from app.core.config import Settings

    return Settings(env="test", database_url=pg_url, secret_key=secrets.token_urlsafe(48),
                    upload_dir=str(tmp_path / "uploads"), max_upload_bytes=64 * 1024)


@pytest.fixture
def app(settings):
    engine = create_engine(settings.database_url)
    with engine.begin() as c:
        c.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    engine.dispose()
    from app.main import create_app

    application = create_app(settings, fakeredis.FakeRedis())
    yield application
    application.state.engine.dispose()


def make_client(app, raise_errors: bool = True) -> TestClient:
    return TestClient(app, base_url="https://testserver", raise_server_exceptions=raise_errors)


@dataclass
class Actor:
    name: str
    email: str
    password: str
    id: uuid.UUID
    client: TestClient | None = None
    csrf: str = ""

    def login(self, app) -> "Actor":
        self.client = make_client(app)
        r = self.client.post("/api/v1/auth/login", json={"email": self.email, "password": self.password})
        assert r.status_code == 200, r.text
        self.csrf = r.json()["csrf_token"]
        self.client.headers["X-CSRF-Token"] = self.csrf
        return self


@dataclass
class World:
    ws_a: uuid.UUID
    ws_b: uuid.UUID
    actors: dict[str, Actor] = field(default_factory=dict)
    ids: dict[str, uuid.UUID] = field(default_factory=dict)
    invite_token: str = ""

    def __getattr__(self, name: str):
        d = self.__dict__
        if name in d.get("actors", {}):
            return d["actors"][name]
        if name in d.get("ids", {}):
            return d["ids"][name]
        raise AttributeError(name)

    def url(self, path: str, ws: str = "a") -> str:
        return f"/api/v1/workspaces/{self.ws_a if ws == 'a' else self.ws_b}{path}"


def new_password() -> str:
    return "Lab-" + secrets.token_urlsafe(18)


@pytest.fixture
def world(app) -> World:
    from app.core.security import hash_password
    from app.models import Membership, User, Workspace

    maker = app.state.sessionmaker
    w = World(ws_a=uuid.uuid4(), ws_b=uuid.uuid4())
    people = [("alice", "owner", "a"), ("adam", "manager", "a"), ("bob", "member", "a"), ("vera", "viewer", "a"),
              ("mallory", "owner", "b"), ("root", None, None)]
    with maker() as s:
        s.add_all([Workspace(id=w.ws_a, name="Workspace A"), Workspace(id=w.ws_b, name="Workspace B")])
        s.flush()
        for name, role, ws in people:
            pw = new_password()
            u = User(email=f"{name}@lab.test", display_name=name.title(), password_hash=hash_password(pw),
                     is_platform_admin=(name == "root"))
            s.add(u)
            s.flush()
            if role:
                s.add(Membership(workspace_id=w.ws_a if ws == "a" else w.ws_b, user_id=u.id, role=role))
            w.actors[name] = Actor(name, u.email, pw, u.id)
        s.commit()
    for a in w.actors.values():
        a.login(app)

    def make(owner: Actor, ws: str, tag: str) -> None:
        cl = owner.client
        t = cl.post(w.url("/tickets", ws), json={"subject": f"Ticket {tag.upper()}", "requester_name": "Requester",
                                                 "requester_email": f"req-{tag}@example.test"})
        assert t.status_code == 201, t.text
        w.ids[f"ticket_{tag}"] = uuid.UUID(t.json()["id"])
        n = cl.post(w.url(f"/tickets/{t.json()['id']}/notes", ws), json={"body": f"secret note {tag}"})
        assert n.status_code == 201, n.text

    make(w.alice, "a", "a")
    make(w.mallory, "b", "b")
    inv = w.alice.client.post(w.url("/invitations"), json={"email": "newcomer@lab.test", "role": "member"})
    assert inv.status_code == 201, inv.text
    w.ids["invitation_a"] = uuid.UUID(inv.json()["id"])
    w.invite_token = inv.json()["invite_url"].split("#", 1)[1]
    return w


def events(app, type_: str | None = None) -> list:
    from sqlalchemy import select

    from app.models import SecurityEvent

    with app.state.sessionmaker() as s:
        stmt = select(SecurityEvent).order_by(SecurityEvent.id)
        if type_:
            stmt = stmt.where(SecurityEvent.type == type_)
        return list(s.scalars(stmt))


def alerts(app, rule: str | None = None) -> list:
    from sqlalchemy import select

    from app.models import Alert

    with app.state.sessionmaker() as s:
        stmt = select(Alert).order_by(Alert.id)
        if rule:
            stmt = stmt.where(Alert.rule == rule)
        return list(s.scalars(stmt))
