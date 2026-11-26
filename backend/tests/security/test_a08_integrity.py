"""A08 Integrity: clients can't set server-owned fields."""

from __future__ import annotations

import pytest

from tests.conftest import make_client


@pytest.mark.parametrize("extra", [{"number": 1}, {"workspace_id": "00000000-0000-0000-0000-000000000000"}, {"created_by": None},
                                   {"status": "closed"}])
def test_ticket_create_rejects_server_owned_fields(app, world, extra):
    body = {"subject": "x", "requester_name": "x", "requester_email": "x@example.test", **extra}
    assert world.bob.client.post(world.url("/tickets"), json=body).status_code == 422


@pytest.mark.parametrize("extra", [{"requester_email": "y@example.test"}, {"number": 5}])
def test_ticket_update_rejects_other_fields(app, world, extra):
    assert world.bob.client.patch(world.url(f"/tickets/{world.ticket_a}"), json=extra).status_code == 422


def test_login_rejects_extra_fields(app, world):
    r = make_client(app).post("/api/v1/auth/login", json={"email": world.bob.email, "password": world.bob.password, "is_platform_admin": True})
    assert r.status_code == 422
