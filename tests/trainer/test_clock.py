"""Virtual time for running upstream routines against the simulator."""

import time

import pytest

import stanza.device
import stanza.routines.builtins.charge_sensor.utils.peak_stability as peak_stability
import stanza.routines.builtins.health_check as health_check
from trainer.clock import PATCHED_MODULES, VirtualClock, virtual_time


def test_clock_starts_at_zero_and_advances() -> None:
    clock = VirtualClock()
    assert clock.now() == 0.0
    clock.advance(1.5)
    clock.sleep(0.5)
    assert clock.now() == 2.0


def test_clock_rejects_negative_steps() -> None:
    clock = VirtualClock()
    with pytest.raises(ValueError, match="negative"):
        clock.advance(-1.0)
    with pytest.raises(ValueError, match="negative"):
        clock.sleep(-0.1)


def test_virtual_time_patches_routine_modules() -> None:
    clock = VirtualClock()
    start = time.perf_counter()
    with virtual_time(clock):
        health_check.time.sleep(10.0)
        peak_stability.time.sleep(120.0)
        assert peak_stability.time.time() == 130.0
        assert health_check.time.monotonic() == 130.0
        assert health_check.time.perf_counter() == 130.0
    assert time.perf_counter() - start < 1.0
    assert clock.now() == 130.0


def test_virtual_time_restores_real_time() -> None:
    with virtual_time(VirtualClock()):
        pass
    for module in PATCHED_MODULES:
        assert module.time is time


def test_virtual_time_restores_on_error() -> None:
    with pytest.raises(RuntimeError), virtual_time(VirtualClock()):
        raise RuntimeError("boom")
    assert stanza.device.time is time


def test_proxy_delegates_other_attributes() -> None:
    with virtual_time(VirtualClock()):
        assert health_check.time.strftime is time.strftime


def test_virtual_time_is_not_reentrant() -> None:
    with virtual_time(VirtualClock()), pytest.raises(RuntimeError, match="already"):
        with virtual_time(VirtualClock()):
            pass
