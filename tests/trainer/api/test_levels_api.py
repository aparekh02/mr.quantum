"""Level endpoints: list levels, start an attempt, hints, submit."""

from typing import Any

from fastapi.testclient import TestClient

from trainer.api.schemas import AttemptInfo, LevelInfo

SENSOR = {
    "peak_spacing": 0.02,
    "sensor_group_name": "side_B",
    "sensor_plunger_gate": "PB",
    "measure_electrode": "OUT_B",
    "bias_gate": "IN_B",
    "bias_voltage": 0.001,
    "settling_time_s": 0,
}


def _start(client: TestClient, level: str = "coulomb-peak") -> dict[str, Any]:
    r = client.post(f"/levels/{level}/attempts")
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    AttemptInfo.model_validate(body)
    return body


def test_list_levels(client: TestClient) -> None:
    levels = [LevelInfo.model_validate(x) for x in client.get("/levels").json()]
    assert levels[0].id == "coulomb-peak"
    assert levels[0].concept
    assert levels[0].hint_count >= 1


def test_unknown_level_is_404(client: TestClient) -> None:
    assert client.post("/levels/nope/attempts").status_code == 404


def test_start_attempt_creates_a_ready_session(client: TestClient) -> None:
    attempt = _start(client)
    sid = attempt["session_id"]
    assert attempt["status"] == "active"
    assert attempt["measurements"] == 0
    assert client.get(f"/sessions/{sid}").json()["device"] == "dqd_with_sensor"
    kinds = {e["kind"] for e in client.get(f"/sessions/{sid}/events").json()}
    assert "sweep" in kinds  # the setup health checks ran and streamed


def test_hints_one_at_a_time(client: TestClient) -> None:
    attempt = _start(client)
    aid = attempt["id"]
    first = client.post(f"/attempts/{aid}/hints").json()
    assert first["hint"] and first["hints_shown"] == 1
    for _ in range(5):
        last = client.post(f"/attempts/{aid}/hints").json()
    assert last["hint"] is None
    assert client.get(f"/attempts/{aid}").json()["hints_shown"] == last["hints_shown"]


def test_play_and_submit(client: TestClient) -> None:
    attempt = _start(client)
    sid, aid = attempt["session_id"], attempt["id"]
    run = client.post(
        f"/sessions/{sid}/runs?wait=true",
        json={"routine": "find_sensor_peak", "parameters": SENSOR},
    ).json()
    assert run["status"] == "succeeded"
    assert client.get(f"/attempts/{aid}").json()["measurements"] > 0
    result = client.post(f"/attempts/{aid}/submit")
    assert result.status_code == 200
    body = AttemptInfo.model_validate(result.json())
    assert body.status == "submitted"
    assert body.evaluation is not None and body.evaluation.success
    assert client.post(f"/attempts/{aid}/submit").status_code == 409


def test_failed_submission_carries_feedback(client: TestClient) -> None:
    attempt = _start(client)
    body = client.post(f"/attempts/{attempt['id']}/submit").json()
    assert body["evaluation"]["success"] is False
    assert body["evaluation"]["feedback"]


def test_unknown_attempt_is_404(client: TestClient) -> None:
    assert client.get("/attempts/nope").status_code == 404
    assert client.post("/attempts/nope/submit").status_code == 404
    assert client.post("/attempts/nope/hints").status_code == 404


def test_cannot_submit_while_a_routine_runs(client: TestClient) -> None:
    from trainer.api.app import get_registry

    attempt = _start(client)
    session = get_registry(client.app).get(attempt["session_id"])
    with session.busy():
        assert client.post(f"/attempts/{attempt['id']}/submit").status_code == 409
