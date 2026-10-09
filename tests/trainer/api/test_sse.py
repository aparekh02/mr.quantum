"""Server-sent events: the same ordered stream as the websocket, for curl."""

import json
from typing import Any

from fastapi.testclient import TestClient

from tests.trainer.api.conftest import new_session


def _parse(lines: list[str]) -> list[dict[str, Any]]:
    events, fields = [], {}
    for line in lines:
        if not line:
            if "data" in fields:
                events.append({"id": int(fields["id"]), **json.loads(fields["data"])})
            fields = {}
        elif not line.startswith(":"):
            key, _, value = line.partition(": ")
            fields[key] = value
    return events


def _run(client: TestClient, sid: str, n: int) -> None:
    r = client.post(
        f"/sessions/{sid}/runs?wait=true",
        json={"routine": "api_test_sweep", "parameters": {"n": n}},
    )
    assert r.json()["status"] == "succeeded"


def test_sse_replays_history_then_ends_without_follow(client: TestClient) -> None:
    sid = new_session(client)
    _run(client, sid, 12)
    r = client.get(f"/sessions/{sid}/events/stream?follow=false")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _parse(r.text.splitlines())
    history = client.get(f"/sessions/{sid}/events").json()
    assert [e["seq"] for e in events] == [e["seq"] for e in history]
    assert all(e["id"] == e["seq"] for e in events)


def test_sse_after_cursor_and_last_event_id(client: TestClient) -> None:
    sid = new_session(client)
    _run(client, sid, 6)
    by_query = _parse(
        client.get(
            f"/sessions/{sid}/events/stream?follow=false&after=3"
        ).text.splitlines()
    )
    by_header = _parse(
        client.get(
            f"/sessions/{sid}/events/stream?follow=false",
            headers={"Last-Event-ID": "3"},
        ).text.splitlines()
    )
    assert by_query == by_header
    assert by_query[0]["seq"] == 4


def test_sse_follows_a_live_run_until_it_finishes(client: TestClient) -> None:
    sid = new_session(client)
    started = client.post(
        f"/sessions/{sid}/runs",
        json={"routine": "api_test_sweep", "parameters": {"n": 150}},
    )
    assert started.status_code == 202, started.text
    received: list[str] = []
    with client.stream("GET", f"/sessions/{sid}/events/stream?until=run_finished") as r:
        for line in r.iter_lines():
            received.append(line)
    events = _parse([*received, ""])
    assert events[-1]["kind"] == "run_finished"
    assert len([e for e in events if e["kind"] == "sweep_point"]) == 150
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))


def test_sse_unknown_session_is_404(client: TestClient) -> None:
    assert client.get("/sessions/nope/events/stream").status_code == 404
