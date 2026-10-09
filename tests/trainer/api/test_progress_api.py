"""Progression over the API: players, unlocking, persisted progress, explanations."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.trainer.api.conftest import DEVICES
from trainer.api.app import create_app
from trainer.api.schemas import AttemptInfo, LevelProgress

SENSOR = {
    "peak_spacing": 0.02,
    "sensor_group_name": "side_B",
    "sensor_plunger_gate": "PB",
    "measure_electrode": "OUT_B",
    "bias_gate": "IN_B",
    "bias_voltage": 0.001,
    "settling_time_s": 0,
}


def _start(client: TestClient, level: str, player: str | None) -> Any:
    body = {} if player is None else {"player": player}
    return client.post(f"/levels/{level}/attempts", json=body)


def _win_level_one(client: TestClient, player: str) -> dict[str, Any]:
    attempt = _start(client, "coulomb-peak", player).json()
    client.post(
        f"/sessions/{attempt['session_id']}/runs?wait=true",
        json={"routine": "find_sensor_peak", "parameters": SENSOR},
    )
    result: dict[str, Any] = client.post(f"/attempts/{attempt['id']}/submit").json()
    return result


def test_new_player_progress(client: TestClient) -> None:
    progress = [
        LevelProgress.model_validate(p)
        for p in client.get("/players/ada/progress").json()
    ]
    assert [(p.id, p.unlocked) for p in progress] == [
        ("coulomb-peak", True),
        ("compensate-sensor", False),
        ("double-dot", False),
    ]


def test_locked_level_is_403_for_a_player(client: TestClient) -> None:
    assert _start(client, "double-dot", "ada").status_code == 403


def test_free_play_without_a_player_is_never_locked(client: TestClient) -> None:
    assert _start(client, "double-dot", None).status_code == 201


def test_invalid_player_is_422(client: TestClient) -> None:
    assert _start(client, "coulomb-peak", "bad player!").status_code == 422
    assert client.get("/players/bad%20player/progress").status_code == 422


def test_winning_level_one_unlocks_level_two_and_explains(client: TestClient) -> None:
    result = _win_level_one(client, "ada")
    AttemptInfo.model_validate(result)
    assert result["evaluation"]["success"]
    assert result["player"] == "ada"
    assert len(result["explanation"]) >= 3
    progress = {p["id"]: p for p in client.get("/players/ada/progress").json()}
    assert progress["coulomb-peak"]["completed"]
    assert progress["coulomb-peak"]["best_score"] == result["evaluation"]["score"]
    assert progress["compensate-sensor"]["unlocked"]
    assert _start(client, "compensate-sensor", "ada").status_code == 201


def test_explanation_is_empty_before_submitting(client: TestClient) -> None:
    attempt = _start(client, "coulomb-peak", None).json()
    assert attempt["explanation"] == []


def test_hints_cost_points_and_are_recorded(client: TestClient) -> None:
    attempt = _start(client, "coulomb-peak", "grace").json()
    client.post(f"/attempts/{attempt['id']}/hints")
    client.post(
        f"/sessions/{attempt['session_id']}/runs?wait=true",
        json={"routine": "find_sensor_peak", "parameters": SENSOR},
    )
    client.post(f"/attempts/{attempt['id']}/submit")
    progress = client.get("/players/grace/progress").json()[0]
    assert progress["hints_used"] == 1


def test_progress_survives_a_restart(tmp_path: Path) -> None:
    progress_file = tmp_path / "progress.json"
    with TestClient(
        create_app(DEVICES, tmp_path / "a", progress_file=progress_file)
    ) as c1:
        _win_level_one(c1, "ada")
    with TestClient(
        create_app(DEVICES, tmp_path / "b", progress_file=progress_file)
    ) as c2:
        assert c2.get("/players/ada/progress").json()[1]["unlocked"]
