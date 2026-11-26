"""A06 Insecure Design: help desk rules are enforced server-side."""

from __future__ import annotations

from tests.conftest import make_client


def new_ticket(w, **extra):
    body = {"subject": "Printer jam", "requester_name": "R", "requester_email": "r@example.test", **extra}
    return w.alice.client.post(w.url("/tickets"), json=body)


def test_ticket_numbers_are_sequential(app, world):
    refs = [new_ticket(world).json()["ref"] for _ in range(2)]
    assert refs == ["HD-1002", "HD-1003"]


def test_last_owner_cannot_be_demoted(app, world):
    assert world.alice.client.put(world.url(f"/members/{world.alice.id}"), json={"role": "manager"}).status_code == 409


def test_removed_agent_loses_access_and_tickets_return_to_queue(app, world):
    world.alice.client.patch(world.url(f"/tickets/{world.ticket_a}"), json={"assignee_id": str(world.bob.id)})
    assert world.adam.client.delete(world.url(f"/members/{world.bob.id}")).status_code == 204
    assert world.bob.client.get(world.url("/tickets")).status_code == 404
    assert world.alice.client.get(world.url(f"/tickets/{world.ticket_a}")).json()["assignee_id"] is None


def test_invitation_is_single_use(app, world):
    body = {"token": world.invite_token, "display_name": "N", "password": "Brand-new-Passphrase-42"}
    assert make_client(app).post("/api/v1/invitations/register", json=body).status_code == 201
    assert make_client(app).post("/api/v1/invitations/register", json=body).status_code == 404


def test_limits(app, world):
    assert new_ticket(world, subject="x" * 201).status_code == 422
    assert new_ticket(world, requester_email="not-an-email").status_code == 422
    assert world.alice.client.get(world.url("/tickets"), params={"limit": 10_000}).status_code == 422
