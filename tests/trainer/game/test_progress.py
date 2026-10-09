"""Persisted player progress and unlocking (trainer/game/progress.py)."""

import json
import threading
from pathlib import Path

import pytest

from trainer.game.levels import LEVELS
from trainer.game.progress import ProgressStore, validate_player


def _store(tmp_path: Path) -> ProgressStore:
    return ProgressStore(tmp_path / "progress.json", LEVELS)


def test_new_player_has_only_level_one_unlocked(tmp_path: Path) -> None:
    view = _store(tmp_path).view("ada")
    assert [(lv["id"], lv["unlocked"], lv["completed"]) for lv in view] == [
        ("coulomb-peak", True, False),
        ("compensate-sensor", False, False),
        ("double-dot", False, False),
    ]


def test_completing_a_level_unlocks_the_next(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record("ada", "coulomb-peak", success=True, score=800, accuracy=0.9, hints=1)
    view = {lv["id"]: lv for lv in store.view("ada")}
    assert view["coulomb-peak"]["completed"]
    assert view["compensate-sensor"]["unlocked"]
    assert not view["double-dot"]["unlocked"]


def test_failed_attempts_count_but_do_not_unlock(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record("ada", "coulomb-peak", success=False, score=0, accuracy=0.0, hints=0)
    first = store.view("ada")[0]
    assert first["attempts"] == 1 and not first["completed"]
    assert not store.view("ada")[1]["unlocked"]


def test_best_score_is_kept(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for s in (500, 900, 700):
        store.record(
            "ada", "coulomb-peak", success=True, score=s, accuracy=s / 1000, hints=0
        )
    first = store.view("ada")[0]
    assert first["best_score"] == 900
    assert first["attempts"] == 3


def test_progress_persists_across_store_instances(tmp_path: Path) -> None:
    _store(tmp_path).record(
        "ada", "coulomb-peak", success=True, score=800, accuracy=0.9, hints=2
    )
    reloaded = _store(tmp_path)
    assert reloaded.view("ada")[0]["best_score"] == 800
    data = json.loads((tmp_path / "progress.json").read_text())
    assert data["players"]["ada"]["coulomb-peak"]["hints_used"] == 2


def test_players_are_independent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record("ada", "coulomb-peak", success=True, score=800, accuracy=0.9, hints=0)
    assert not store.view("grace")[0]["completed"]


def test_is_unlocked(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.is_unlocked("ada", "coulomb-peak")
    assert not store.is_unlocked("ada", "double-dot")
    with pytest.raises(KeyError):
        store.is_unlocked("ada", "nope")


def test_unknown_level_cannot_be_recorded(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        _store(tmp_path).record(
            "ada", "nope", success=True, score=1, accuracy=1.0, hints=0
        )


def test_corrupt_file_is_rejected_not_silently_reset(tmp_path: Path) -> None:
    (tmp_path / "progress.json").write_text("{not json")
    with pytest.raises(ValueError, match="progress"):
        _store(tmp_path)


def test_concurrent_records_lose_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)

    def play(player: str) -> None:
        for _ in range(20):
            store.record(
                player, "coulomb-peak", success=False, score=0, accuracy=0.0, hints=0
            )

    threads = [threading.Thread(target=play, args=(f"p{i}",)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    reloaded = _store(tmp_path)
    assert all(reloaded.view(f"p{i}")[0]["attempts"] == 20 for i in range(5))


@pytest.mark.parametrize("player", ["ada", "Ada_99", "a-b", "x" * 64])
def test_valid_players(player: str) -> None:
    assert validate_player(player) == player


@pytest.mark.parametrize("player", ["", "has space", "../etc", "x" * 65, "é"])
def test_invalid_players(player: str) -> None:
    with pytest.raises(ValueError, match="player"):
        validate_player(player)
