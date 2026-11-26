"""A01 Broken Access Control: every route is covered, workspaces are isolated, roles
hold, CSRF is enforced. Routes are enumerated from the OpenAPI schema, so a new route
without a proper access rule fails these tests automatically."""

from __future__ import annotations

import re
import uuid

import pytest

from tests.conftest import make_client

PUBLIC = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/invitations/preview"),
    ("POST", "/api/v1/invitations/register"),
}
PLATFORM_ADMIN_PREFIX = "/api/v1/admin/"
BODIES = {
    ("POST", "/api/v1/workspaces/{workspace_id}/tickets"): {"json": {"subject": "x", "requester_name": "x", "requester_email": "x@example.test"}},
    ("PATCH", "/api/v1/workspaces/{workspace_id}/tickets/{ticket_id}"): {"json": {"priority": "high"}},
    ("POST", "/api/v1/workspaces/{workspace_id}/tickets/{ticket_id}/notes"): {"json": {"body": "x"}},
    ("PUT", "/api/v1/workspaces/{workspace_id}/members/{user_id}"): {"json": {"role": "viewer"}},
    ("POST", "/api/v1/workspaces/{workspace_id}/invitations"): {"json": {"email": "x@lab.test", "role": "viewer"}},
    ("POST", "/api/v1/auth/password"): {"json": {"current_password": "x", "new_password": "y"}},
    ("POST", "/api/v1/invitations/accept"): {"json": {"token": "x" * 43}},
}


def operations(app) -> list[tuple[str, str]]:
    ops = []
    for path, item in app.openapi()["paths"].items():
        for method in item:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                ops.append((method.upper(), path))
    return sorted(ops)


def fill(path: str, w, ws: str = "a", res: str = "a") -> str:
    values = {
        "workspace_id": w.ws_a if ws == "a" else w.ws_b,
        "ticket_id": w.ids[f"ticket_{res}"],
        "invitation_id": w.ids["invitation_a"],
        "user_id": w.bob.id,
        "alert_id": 1,
    }

    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in values:
            pytest.fail(f"route parameter {{{name}}} has no test value; add it to fill() in {__file__}")
        return str(values[name])

    return re.sub(r"{(\w+)}", sub, path)


def call(client, method, path, template):
    return client.request(method, path, **BODIES.get((method, template), {}))


def test_route_table_is_known(app):
    assert len(operations(app)) >= 20


def test_every_non_public_route_requires_authentication(app, world):
    anon = make_client(app)
    for method, path in operations(app):
        if (method, path) in PUBLIC:
            continue
        r = call(anon, method, fill(path, world), path)
        assert r.status_code == 401, f"{method} {path} -> {r.status_code}"


def test_every_workspace_route_hides_other_workspaces(app, world):
    for method, path in operations(app):
        if "{workspace_id}" not in path:
            continue
        r = call(world.mallory.client, method, fill(path, world), path)
        assert r.status_code == 404, f"{method} {path} as non-member -> {r.status_code}"


def test_resource_ids_cannot_cross_workspaces_via_own_workspace(app, world):
    """Mallory uses HER workspace in the path but workspace A's resource IDs."""
    for method, path in operations(app):
        if "{workspace_id}" not in path or path.count("{") < 2 or "{user_id}" in path:
            continue
        r = call(world.mallory.client, method, fill(path, world, ws="b", res="a"), path)
        assert r.status_code == 404, f"{method} {path} cross-workspace id -> {r.status_code}"


def test_platform_admin_routes_are_hidden_from_everyone_else(app, world):
    for method, path in operations(app):
        if not path.startswith(PLATFORM_ADMIN_PREFIX):
            continue
        for who in ("alice", "mallory", "bob"):
            r = call(getattr(world, who).client, method, fill(path, world), path)
            assert r.status_code == 404, f"{who} {method} {path} -> {r.status_code}"
    assert world.root.client.get("/api/v1/admin/alerts").status_code == 200


@pytest.mark.parametrize("who,method,path,body,status", [
    ("vera", "POST", "/tickets", {"subject": "x", "requester_name": "x", "requester_email": "x@example.test"}, 403),
    ("vera", "POST", "/tickets/{ticket}/notes", {"body": "x"}, 403),
    ("vera", "PATCH", "/tickets/{ticket}", {"priority": "high"}, 403),
    ("bob", "PATCH", "/tickets/{ticket}", {"status": "closed"}, 403),       # agents resolve, leads close
    ("bob", "PATCH", "/tickets/{ticket}", {"status": "resolved"}, 200),
    ("bob", "POST", "/invitations", {"email": "z@lab.test"}, 403),
    ("bob", "PUT", "/members/{bob}", {"role": "owner"}, 403),
    ("adam", "PUT", "/members/{bob}", {"role": "manager"}, 403),
    ("adam", "PATCH", "/tickets/{ticket}", {"status": "closed"}, 200),
])
def test_role_matrix(app, world, who, method, path, body, status):
    url = world.url(path.format(ticket=world.ticket_a, bob=world.bob.id))
    r = getattr(world, who).client.request(method, url, json=body)
    assert r.status_code == status, r.text


def test_assignee_must_be_member(app, world):
    r = world.alice.client.patch(world.url(f"/tickets/{world.ticket_a}"), json={"assignee_id": str(world.mallory.id)})
    assert r.status_code == 422


def test_csrf_header_required_on_writes(app, world):
    c = make_client(app)
    c.cookies = world.alice.client.cookies
    url = world.url(f"/tickets/{world.ticket_a}/notes")
    assert c.post(url, json={"body": "x"}).status_code == 403
    assert c.post(url, json={"body": "x"}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert c.post(url, json={"body": "x"}, headers={"X-CSRF-Token": world.alice.csrf}).status_code == 201
    assert c.get(url).status_code == 200


def test_csrf_token_of_another_session_is_rejected(app, world):
    c = make_client(app)
    c.cookies = world.alice.client.cookies
    r = c.post(world.url(f"/tickets/{world.ticket_a}/notes"), json={"body": "x"}, headers={"X-CSRF-Token": world.bob.csrf})
    assert r.status_code == 403


@pytest.mark.parametrize("ctype", ["application/x-www-form-urlencoded", "text/plain", "multipart/form-data; boundary=x"])
def test_cross_site_form_content_types_are_refused(app, world, ctype):
    r = world.alice.client.post(world.url(f"/tickets/{world.ticket_a}/notes"), content=b"body=x",
                                headers={"Content-Type": ctype})
    assert r.status_code == 415




def test_invitation_bound_to_invited_email(app, world):
    r = world.bob.client.post("/api/v1/invitations/accept", json={"token": world.invite_token})
    assert r.status_code == 403
    assert world.bob.client.get(world.url("/invitations")).status_code == 403


def test_unknown_ids_and_bad_uuids(app, world):
    c = world.alice.client
    assert c.get(world.url(f"/tickets/{uuid.uuid4()}")).status_code == 404
    assert c.get(f"/api/v1/workspaces/{uuid.uuid4()}/tickets").status_code == 404
    assert c.get(world.url("/tickets/1%20OR%201=1")).status_code == 422


def test_no_route_redirects(app, world):
    for method, path in operations(app):
        if method != "GET":
            continue
        r = world.alice.client.get(fill(path, world), follow_redirects=False)
        assert not 300 <= r.status_code < 400, path
