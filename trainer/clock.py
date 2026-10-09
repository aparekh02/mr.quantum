"""Simulated wall-clock time for running upstream routines on the simulator.

Upstream routines wait for real hardware to settle (``time.sleep``) and time
stability holds with ``time.time()``. Against a simulator those waits are pure
delay. :func:`virtual_time` swaps the ``time`` attribute of upstream's routine
modules for a proxy driven by a :class:`VirtualClock`, so routine code runs
unmodified while waits take no wall time and stay deterministic.
"""

from __future__ import annotations

import time as _real_time
from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType
from typing import Any

import stanza.device
import stanza.routines.builtins.charge_sensor.charge_sensor_compensation
import stanza.routines.builtins.charge_sensor.charge_sensor_readout
import stanza.routines.builtins.charge_sensor.utils.peak_stability
import stanza.routines.builtins.health_check

PATCHED_MODULES: tuple[ModuleType, ...] = (
    stanza.device,
    stanza.routines.builtins.health_check,
    stanza.routines.builtins.charge_sensor.charge_sensor_compensation,
    stanza.routines.builtins.charge_sensor.charge_sensor_readout,
    stanza.routines.builtins.charge_sensor.utils.peak_stability,
)
"""Upstream modules that bind ``time`` at import and call it in routines."""

_active = False


class VirtualClock:
    """A monotonically advancing simulated clock, in seconds."""

    def __init__(self) -> None:
        self._now = 0.0

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError(f"cannot advance by a negative time: {seconds}")
        self._now += seconds

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError(f"sleep length must be non-negative, got {seconds}")
        self.advance(seconds)


class _VirtualTimeModule:
    """Stands in for the ``time`` module: clock functions are virtual."""

    def __init__(self, clock: VirtualClock) -> None:
        self._clock = clock

    def sleep(self, seconds: float) -> None:
        self._clock.sleep(seconds)

    def time(self) -> float:
        return self._clock.now()

    def monotonic(self) -> float:
        return self._clock.now()

    def perf_counter(self) -> float:
        return self._clock.now()

    def __getattr__(self, name: str) -> Any:
        return getattr(_real_time, name)


@contextmanager
def virtual_time(clock: VirtualClock) -> Iterator[VirtualClock]:
    """Run upstream routines with ``clock`` as their wall clock."""
    global _active
    if _active:
        raise RuntimeError("virtual time is already active")
    proxy = _VirtualTimeModule(clock)
    _active = True
    try:
        for module in PATCHED_MODULES:
            vars(module)["time"] = proxy
        yield clock
    finally:
        for module in PATCHED_MODULES:
            vars(module)["time"] = _real_time
        _active = False
