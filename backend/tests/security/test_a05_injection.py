"""A05 Injection: search and filters are parameterised and typed; output is JSON;
validation errors don't reflect input."""

from __future__ import annotations

import pytest

SQLI = ["' OR '1'='1", "'; DROP TABLE tickets; --", "%' AND pg_sleep(3) IS NULL AND '%'='", "%", "_"]


@pytest.mark.parametrize("payload", SQLI)
def test_ticket_search_is_parameterised(app, world, payload):
    r = world.alice.client.get(world.url("/tickets"), params={"q": payload})
    assert r.status_code == 200 and r.json() == []


@pytest.mark.parametrize("param,value", [("status", "open' OR '1'='1"), ("assignee", "me'--"), ("limit", "5;DROP")])
def test_filters_are_typed(app, world, param, value):
    assert world.alice.client.get(world.url("/tickets"), params={param: value}).status_code == 422


def test_html_is_stored_as_data(app, world):
    payload = "<script>alert(1)</script>"
    c = world.alice.client
    r = c.post(world.url(f"/tickets/{world.ticket_a}/notes"), json={"body": payload})
    assert r.status_code == 201 and r.headers["content-type"].startswith("application/json")
    assert c.get(world.url(f"/tickets/{world.ticket_a}/notes")).json()[-1]["body"] == payload


def test_validation_errors_do_not_reflect_input(app, world):
    marker = "<svg/onload=alert(1)>"
    r = world.alice.client.get(world.url("/tickets"), params={"status": marker})
    assert r.status_code == 422 and "onload" not in r.text
