"""Contract tests for the trainer API (trainer/api/app.py)."""

from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tests.trainer.api.conftest import new_session
from trainer.api.schemas import (
    DeviceInfo,
    EventOut,
    PadInfo,
    RoutineInfo,
    RunInfo,
    SessionInfo,
)

SENSOR_HEALTH = [
    ("noise_floor_measurement", {"measure_electrode": "OUT_B", "num_points": 50}),
    ("leakage_test", {"leakage_threshold_resistance": 50_000_000, "num_points": 10}),
]
SWEEP_B = {
    "measure_electrode": "OUT_B",
    "bias_gate": "IN_B",
    "bias_voltage": 0.001,
    "charge_carrier_type": "hole",
    "step_size": 0.01,
}


def _run(client: TestClient, sid: str, name: str, **params: Any) -> dict[str, Any]:
    r = client.post(
        f"/sessions/{sid}/runs?wait=true", json={"routine": name, "parameters": params}
    )
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    RunInfo.model_validate(body)
    return body


# --- devices and sessions -----------------------------------------------------


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_list_devices(client: TestClient) -> None:
    devices = [DeviceInfo.model_validate(d) for d in client.get("/devices").json()]
    names = {d.name for d in devices}
    assert {"single_channel", "dqd_with_sensor"} <= names


def test_create_and_get_session(client: TestClient) -> None:
    sid = new_session(client)
    info = SessionInfo.model_validate(client.get(f"/sessions/{sid}").json())
    assert info.device == "dqd_with_sensor"
    assert set(info.groups) == {"side_A", "side_B"}


def test_unknown_device_is_422(client: TestClient) -> None:
    r = client.post("/sessions", json={"device": "flux_capacitor"})
    assert r.status_code == 422


def test_malformed_session_body_is_422(client: TestClient) -> None:
    assert client.post("/sessions", json={"nope": 1}).status_code == 422


def test_unknown_session_is_404(client: TestClient) -> None:
    assert client.get("/sessions/does-not-exist").status_code == 404
    assert client.get("/sessions/does-not-exist/pads").status_code == 404


def test_delete_session(client: TestClient) -> None:
    sid = new_session(client)
    assert client.delete(f"/sessions/{sid}").status_code == 204
    assert client.get(f"/sessions/{sid}").status_code == 404


# --- pads and voltages ---------------------------------------------------------


def test_list_pads(client: TestClient) -> None:
    sid = new_session(client)
    pads = [
        PadInfo.model_validate(p) for p in client.get(f"/sessions/{sid}/pads").json()
    ]
    by_name = {p.name: p for p in pads}
    assert by_name["PB"].pad_type == "GATE"
    assert by_name["PB"].electrode_type == "PLUNGER"
    assert by_name["PB"].group == "side_B"
    assert (by_name["PB"].v_lower_bound, by_name["PB"].v_upper_bound) == (-2.0, 0.3)
    assert by_name["OUT_B"].measurable and not by_name["OUT_B"].controllable
    assert by_name["IN_B"].controllable and not by_name["IN_B"].measurable


def test_set_and_get_voltages(client: TestClient) -> None:
    sid = new_session(client)
    r = client.put(f"/sessions/{sid}/voltages", json={"voltages": {"PB": -0.5}})
    assert r.status_code == 200
    assert r.json()["PB"] == -0.5
    assert client.get(f"/sessions/{sid}/voltages").json()["PB"] == -0.5


@pytest.mark.parametrize(
    "voltages",
    [
        {"PB": -5.0},  # out of bounds
        {"PB": 0.31},  # just above the upper bound
        {"NOPE": 0.0},  # unknown pad
        {"OUT_B": 0.0},  # measure-only contact
        {"PB": "low"},  # not a number
    ],
)
def test_bad_voltages_are_422_and_change_nothing(
    client: TestClient, voltages: dict[str, Any]
) -> None:
    sid = new_session(client)
    r = client.put(f"/sessions/{sid}/voltages", json={"voltages": voltages})
    assert r.status_code == 422, r.text
    assert client.get(f"/sessions/{sid}/voltages").json()["PB"] == 0.0


def test_non_finite_voltage_is_422(client: TestClient) -> None:
    sid = new_session(client)
    r = client.put(
        f"/sessions/{sid}/voltages",
        content='{"voltages": {"PB": NaN}}',
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422


def test_voltage_at_bound_is_accepted(client: TestClient) -> None:
    sid = new_session(client)
    r = client.put(f"/sessions/{sid}/voltages", json={"voltages": {"PB": -2.0}})
    assert r.status_code == 200


def test_measure(client: TestClient) -> None:
    sid = new_session(client)
    r = client.post(f"/sessions/{sid}/measure", json={"pads": ["OUT_B", "PB"]})
    assert r.status_code == 200
    currents = r.json()["currents"]
    assert set(currents) == {"OUT_B", "PB"}
    assert all(isinstance(v, float) for v in currents.values())


@pytest.mark.parametrize("pads", [["NOPE"], ["IN_B"], []])
def test_bad_measure_is_422(client: TestClient, pads: list[str]) -> None:
    sid = new_session(client)
    assert (
        client.post(f"/sessions/{sid}/measure", json={"pads": pads}).status_code == 422
    )


# --- routines --------------------------------------------------------------------


def test_list_routines_describes_parameters(client: TestClient) -> None:
    sid = new_session(client)
    routines = {
        r["name"]: RoutineInfo.model_validate(r)
        for r in client.get(f"/sessions/{sid}/routines").json()
    }
    params = {p.name: p for p in routines["find_sensor_peak"].parameters}
    assert params["peak_spacing"].required
    assert params["peak_spacing"].type == "float"
    assert not params["settling_time_s"].required
    assert params["settling_time_s"].default == 3.0
    assert "ctx" not in params and "session" not in params


def test_run_a_routine_and_fetch_it(client: TestClient) -> None:
    sid = new_session(client)
    run = _run(
        client, sid, "noise_floor_measurement", measure_electrode="OUT_B", num_points=20
    )
    assert run["status"] == "succeeded"
    assert set(run["result"]) == {"current_mean", "current_std"}
    fetched = client.get(f"/sessions/{sid}/runs/{run['id']}").json()
    assert fetched == run
    assert [r["id"] for r in client.get(f"/sessions/{sid}/runs").json()] == [run["id"]]


def test_run_without_wait_returns_202_and_finishes(client: TestClient) -> None:
    sid = new_session(client)
    r = client.post(
        f"/sessions/{sid}/runs",
        json={
            "routine": "noise_floor_measurement",
            "parameters": {"measure_electrode": "OUT_B"},
        },
    )
    assert r.status_code == 202
    run_id = r.json()["id"]
    final = client.get(f"/sessions/{sid}/runs/{run_id}?wait=true").json()
    assert final["status"] == "succeeded"


@pytest.mark.parametrize(
    "body",
    [
        {"routine": "not_a_routine", "parameters": {}},
        {"routine": "find_sensor_peak", "parameters": {}},  # missing required
        {"routine": "noise_floor_measurement", "parameters": {"num_points": "many"}},
        {
            "routine": "noise_floor_measurement",
            "parameters": {"measure_electrode": "OUT_B", "typo_param": 1},
        },
        {
            "routine": "noise_floor_measurement",
            "parameters": {"measure_electrode": "OUT_B", "group": "side_Z"},
        },
        {"parameters": {}},
    ],
)
def test_bad_run_requests_are_422(client: TestClient, body: dict[str, Any]) -> None:
    sid = new_session(client)
    r = client.post(f"/sessions/{sid}/runs?wait=true", json=body)
    assert r.status_code == 422, r.text
    assert client.get(f"/sessions/{sid}/runs").json() == []


def test_unknown_run_is_404(client: TestClient) -> None:
    sid = new_session(client)
    assert client.get(f"/sessions/{sid}/runs/nope").status_code == 404


def test_failing_routine_is_reported_not_500(client: TestClient) -> None:
    sid = new_session(client)
    # global_accumulation needs leakage_test results first: upstream raises.
    r = client.post(
        f"/sessions/{sid}/runs?wait=true",
        json={"routine": "global_accumulation", "parameters": SWEEP_B},
    )
    assert r.status_code == 200
    run = r.json()
    assert run["status"] == "failed"
    assert "global_accumulation" in run["error"]


def test_failure_mid_run_restores_the_pre_run_voltages(client: TestClient) -> None:
    sid = new_session(client)
    client.put(
        f"/sessions/{sid}/voltages", json={"voltages": {"PB": -0.4, "BB0": -0.6}}
    )
    before = client.get(f"/sessions/{sid}/voltages").json()
    run = _run(client, sid, "api_test_moves_then_raises", gate="PB", voltage=-1.5)
    assert run["status"] == "failed"
    assert run["restored_voltages"] is True
    assert client.get(f"/sessions/{sid}/voltages").json() == before


def test_busy_session_rejects_concurrent_changes(client: TestClient) -> None:
    from trainer.api.app import get_registry

    sid = new_session(client)
    session = get_registry(client.app).get(sid)
    with session.busy():
        r = client.post(
            f"/sessions/{sid}/runs",
            json={
                "routine": "noise_floor_measurement",
                "parameters": {"measure_electrode": "OUT_B"},
            },
        )
        assert r.status_code == 409
        r = client.put(f"/sessions/{sid}/voltages", json={"voltages": {"PB": -0.4}})
        assert r.status_code == 409
        assert (
            client.post(f"/sessions/{sid}/measure", json={"pads": ["PB"]}).status_code
            == 409
        )


def test_grouped_runs_and_results_flow_into_later_routines(client: TestClient) -> None:
    sid = new_session(client)
    for name, params in SENSOR_HEALTH:
        assert (
            _run(client, sid, name, group="side_B", **params)["status"] == "succeeded"
        )
    run = _run(client, sid, "global_accumulation", group="side_B", **SWEEP_B)
    assert run["status"] == "succeeded"
    assert run["result"]["global_turn_on_voltage"] < 0  # holes


# --- events and streaming ------------------------------------------------------------


def _events(client: TestClient, sid: str, after: int = 0) -> list[dict[str, Any]]:
    r = client.get(f"/sessions/{sid}/events?after={after}")
    assert r.status_code == 200
    out: list[dict[str, Any]] = r.json()
    for e in out:
        EventOut.model_validate(e)
    return out


def test_events_bracket_a_run_and_carry_every_point(client: TestClient) -> None:
    sid = new_session(client)
    _run(client, sid, "api_test_sweep", n=40)
    events = _events(client, sid)
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "run_started" and kinds[-1] == "run_finished"
    points = [e for e in events if e["kind"] == "sweep_point"]
    assert [p["data"]["x"][0] for p in points] == pytest.approx(
        list(np.linspace(-1.0, -0.5, 40))
    )
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))


def test_events_after_cursor(client: TestClient) -> None:
    sid = new_session(client)
    _run(client, sid, "api_test_sweep", n=5)
    all_events = _events(client, sid)
    assert _events(client, sid, after=3) == all_events[3:]
    assert client.get(f"/sessions/{sid}/events?after=-1").status_code == 422


def test_voltage_changes_are_events(client: TestClient) -> None:
    sid = new_session(client)
    client.put(f"/sessions/{sid}/voltages", json={"voltages": {"PB": -0.4}})
    (event,) = _events(client, sid)
    assert event["kind"] == "voltages"
    assert event["data"] == {"PB": -0.4}


def test_websocket_delivers_points_in_order_without_loss(client: TestClient) -> None:
    sid = new_session(client)
    with client.websocket_connect(f"/sessions/{sid}/stream") as ws:
        response = client.post(
            f"/sessions/{sid}/runs",
            json={"routine": "api_test_sweep", "parameters": {"n": 200}},
        )
        assert response.status_code == 202, response.text
        run = response.json()
        received = []
        for _ in range(1000):
            event = ws.receive_json()
            received.append(event)
            if event["kind"] in {"run_finished", "run_failed"}:
                break
    assert (
        client.get(f"/sessions/{sid}/runs/{run['id']}?wait=true").json()["status"]
        == "succeeded"
    )
    assert received == _events(client, sid)
    assert len([e for e in received if e["kind"] == "sweep_point"]) == 200


def test_websocket_resumes_from_cursor(client: TestClient) -> None:
    sid = new_session(client)
    _run(client, sid, "api_test_sweep", n=10)
    history = _events(client, sid)
    with client.websocket_connect(f"/sessions/{sid}/stream?after=4") as ws:
        replay = [ws.receive_json() for _ in range(len(history) - 4)]
    assert replay == history[4:]


def test_websocket_unknown_session_closes(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/sessions/nope/stream") as ws,
    ):
        ws.receive_json()
