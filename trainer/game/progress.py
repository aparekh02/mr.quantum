"""Persisted per-player progress: attempts, completions, best scores, unlocking.

Players are anonymous ids (no accounts). Progress lives in one JSON file, written
atomically, so it survives restarts. Level n unlocks when level n-1 is completed.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from trainer.game.level import Level

_PLAYER = re.compile(r"^[A-Za-z0-9_-]{1,64}$", re.ASCII)


def validate_player(player: str) -> str:
    if not _PLAYER.match(player):
        raise ValueError(
            f"player must be 1-64 letters, digits, '_' or '-', got {player!r}"
        )
    return player


class ProgressStore:
    def __init__(self, path: Path, levels: Sequence[Level]) -> None:
        self.path = Path(path)
        self.levels = sorted(levels, key=lambda lv: lv.order)
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {"version": 1, "players": {}}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text())
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"progress file {self.path} is not valid JSON: {e}"
                ) from e
            if not isinstance(loaded, dict) or not isinstance(
                loaded.get("players"), dict
            ):
                raise ValueError(f"progress file {self.path} has an unexpected shape")
            self._data = loaded

    def _level(self, level_id: str) -> Level:
        for level in self.levels:
            if level.id == level_id:
                return level
        raise KeyError(f"no level {level_id!r}")

    def _records(self, player: str) -> dict[str, Any]:
        players: dict[str, Any] = self._data["players"]
        records: dict[str, Any] = players.setdefault(validate_player(player), {})
        return records

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=self.path.parent, prefix=".progress-", suffix=".json"
        )
        with os.fdopen(fd, "w") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    def record(
        self,
        player: str,
        level_id: str,
        success: bool,
        score: int,
        accuracy: float,
        hints: int,
    ) -> None:
        self._level(level_id)
        with self._lock:
            entry = self._records(player).setdefault(
                level_id,
                {
                    "attempts": 0,
                    "completed": False,
                    "best_score": 0,
                    "best_accuracy": 0.0,
                    "hints_used": 0,
                },
            )
            entry["attempts"] += 1
            entry["hints_used"] += hints
            if success:
                entry["completed"] = True
                entry["best_score"] = max(entry["best_score"], score)
                entry["best_accuracy"] = max(entry["best_accuracy"], accuracy)
            self._save()

    def view(self, player: str) -> list[dict[str, Any]]:
        with self._lock:
            records = dict(self._records(player))
        out, previous_done = [], True
        for level in self.levels:
            entry = records.get(level.id, {})
            completed = bool(entry.get("completed", False))
            out.append(
                {
                    "id": level.id,
                    "order": level.order,
                    "unlocked": previous_done,
                    "completed": completed,
                    "attempts": int(entry.get("attempts", 0)),
                    "best_score": int(entry.get("best_score", 0)),
                    "best_accuracy": float(entry.get("best_accuracy", 0.0)),
                    "hints_used": int(entry.get("hints_used", 0)),
                }
            )
            previous_done = completed
        return out

    def is_unlocked(self, player: str, level_id: str) -> bool:
        self._level(level_id)
        return bool(
            next(v["unlocked"] for v in self.view(player) if v["id"] == level_id)
        )
