"""One player's attempt at a level."""

from __future__ import annotations

from pathlib import Path

from trainer.game.level import Evaluation, Level
from trainer.lab import SimulatedLab
from trainer.workflows import run_steps


class AttemptClosed(Exception):
    """The attempt was already submitted."""


class Attempt:
    def __init__(self, level: Level, lab: SimulatedLab) -> None:
        self.level = level
        self.lab = lab
        self.hints_shown = 0
        self.result: Evaluation | None = None
        self._baseline = lab.simulator.reading_count

    @classmethod
    def start(
        cls,
        level: Level,
        devices_dir: Path,
        data_dir: Path,
        reuse: Attempt | None = None,
        lab: SimulatedLab | None = None,
    ) -> Attempt:
        """Build the level's device and run its setup.

        ``reuse`` copies another attempt's post-setup results and voltages instead
        of re-running the setup (same level, same device).
        """
        lab = lab or SimulatedLab.from_yaml(
            devices_dir / f"{level.device}.yaml", data_dir
        )
        if reuse is not None:
            for key in reuse.lab.runner.results.list_results():
                lab.runner.results.store(key, reuse.lab.runner.results[key])
            lab.runner.resources.add("group", reuse.lab.runner.resources.get("group"))
            lab.device.jump(reuse.setup_state)
        else:
            run_steps(lab, level.setup)
        attempt = cls(level, lab)
        attempt.setup_state = dict(lab.simulator.state)
        return attempt

    setup_state: dict[str, float]

    @property
    def measurements(self) -> int:
        """Readings the player has taken since the attempt started."""
        return self.lab.simulator.reading_count - self._baseline

    def next_hint(self) -> str | None:
        if self.hints_shown >= len(self.level.hints):
            return None
        hint = self.level.hints[self.hints_shown]
        self.hints_shown += 1
        return hint

    def submit(self) -> Evaluation:
        if self.result is not None:
            raise AttemptClosed()
        self.result = self.level.judge(self)
        return self.result
