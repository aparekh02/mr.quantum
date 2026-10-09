"""A simulated lab: upstream's RoutineRunner wired to the simulator.

Everything a routine touches goes through upstream Stanza: the device comes from
``device_from_config`` (``driver: simulator``), routines run via ``RoutineRunner``.
The lab adds only what a simulated bench needs: the local models client in place
of the cloud SDK, virtual time for settling waits, and a run history.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stanza.device import Device
from stanza.drivers.simulator import Simulator
from stanza.models import DeviceConfig
from stanza.routines import RoutineRunner
from stanza.utils import load_device_config
from trainer.clock import VirtualClock
from trainer.clock import virtual_time as _virtual_time
from trainer.models.client import LocalModelsClient
from trainer.routines import register_builtin_routines


@dataclass(frozen=True)
class RunRecord:
    """One routine invocation."""

    routine: str
    group: str | None
    params: dict[str, Any]
    ok: bool
    error: str | None = None


class SimulatedLab:
    """Owns one simulated device and the runner that drives it."""

    def __init__(self, config: DeviceConfig, base_dir: str | Path) -> None:
        register_builtin_routines()
        self.config = config
        self.runner = RoutineRunner(configs=[config], base_dir=base_dir)
        self.models_client = LocalModelsClient()
        self.runner.resources.add("models_client", self.models_client)
        self.history: list[RunRecord] = []
        instrument = self.device.control_instrument
        if not isinstance(instrument, Simulator):
            raise TypeError("SimulatedLab needs a device driven by the simulator")
        self.simulator = instrument

    @classmethod
    def from_yaml(cls, path: str | Path, base_dir: str | Path) -> SimulatedLab:
        return cls(load_device_config(path), base_dir)

    @property
    def device(self) -> Device:
        device: Device = self.runner.resources.device
        return device

    @contextmanager
    def virtual_time(self) -> Iterator[VirtualClock]:
        """Run code with the simulator's clock standing in for wall time."""
        with _virtual_time(self.simulator.clock) as clock:
            yield clock

    def run(self, routine: str, **params: Any) -> Any:
        """Run an upstream routine in virtual time and record the outcome."""
        group = params.get("group")
        try:
            with self.virtual_time():
                result = self.runner.run(routine, **params)
        except Exception as e:
            self.history.append(
                RunRecord(routine, group, params, ok=False, error=str(e))
            )
            raise
        self.history.append(RunRecord(routine, group, params, ok=True))
        return result

    def clear_group(self) -> None:
        """Undo a previous run's group filter.

        ``RoutineRunner.run(group=...)`` leaves the group resource in place for every
        later run; an ungrouped routine would silently see only that group.
        """
        self.runner.resources.add("group", None)

    def alias_group_results(self, group: str) -> list[str]:
        """Copy ``<routine>_<group>`` results to ``<routine>``; return the routines.

        Some upstream routines (the DQD search) read health-check results without a
        group suffix even when those checks ran per group.
        """
        suffix = f"_{group}"
        aliased = []
        for key in self.runner.results.list_results():
            if key.endswith(suffix):
                name = key[: -len(suffix)]
                self.runner.results.store(name, self.runner.results[key])
                aliased.append(name)
        return aliased
