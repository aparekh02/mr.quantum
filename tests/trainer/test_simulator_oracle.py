"""The simulator's read-only ground-truth oracle, used by level judges."""

from pathlib import Path

import pytest

from stanza.drivers.simulator import Simulator
from tests.trainer.conftest import DQD_YAML
from trainer.lab import SimulatedLab


@pytest.fixture
def sim(tmp_path: Path) -> Simulator:
    lab = SimulatedLab.from_yaml(DQD_YAML, base_dir=tmp_path)
    lab.device.jump(
        {"RB1": -1.7, "RB2": -1.7, "BB0": -1.1, "BB1": -1.1, "PB": -0.63, "IN_B": 0.001}
    )
    return lab.simulator


def test_reading_count_counts_every_measurement(sim: Simulator) -> None:
    start = sim.reading_count
    sim.measure("OUT_B")
    sim.measure(["OUT_B", "PB"])
    assert sim.reading_count == start + 3


def test_ideal_current_has_no_side_effects(sim: Simulator) -> None:
    clock, readings, state = sim.clock.now(), sim.reading_count, dict(sim.state)
    rng_state = sim.rng.bit_generator.state
    sim.ideal_current("OUT_B", {"PB": -0.7})
    assert sim.clock.now() == clock
    assert sim.reading_count == readings
    assert sim.state == state
    assert sim.rng.bit_generator.state == rng_state


def test_ideal_current_matches_a_noiseless_reading(tmp_path: Path) -> None:
    import yaml

    from stanza.models import DeviceConfig

    data = yaml.safe_load(DQD_YAML.read_text())
    sim_cfg = data["instruments"][0]["simulation"]
    sim_cfg["noise_std"] = 0.0
    sim_cfg.pop("charge_noise")
    lab = SimulatedLab(DeviceConfig.model_validate(data), base_dir=tmp_path)
    lab.device.jump({"RB1": -1.7, "RB2": -1.7, "BB0": -1.1, "BB1": -1.1, "IN_B": 0.001})
    oracle = lab.simulator.ideal_current("OUT_B", {"PB": -0.64})
    lab.device.jump({"PB": -0.64})
    assert lab.device.measure("OUT_B") == pytest.approx(oracle, rel=1e-12)


def test_ideal_current_ignores_charge_noise(sim: Simulator) -> None:
    a = sim.ideal_current("OUT_B", {})
    for _ in range(200):
        sim.measure("OUT_B")  # advances time, so the charge noise wanders
    assert sim.ideal_current("OUT_B", {}) == pytest.approx(a, rel=1e-12)


def test_ideal_current_rejects_unknown_pads(sim: Simulator) -> None:
    with pytest.raises(KeyError):
        sim.ideal_current("OUT_B", {"NOPE": 0.0})


def test_dot_openness(sim: Simulator) -> None:
    pinched = sim.dot_openness("SD")
    assert 0.0 <= pinched <= 1.0
    sim.set_voltage("PB", -1.9)
    assert sim.dot_openness("SD") > pinched
    with pytest.raises(KeyError):
        sim.dot_openness("NOPE")


def test_induced_charges_and_gate_turn_on(sim: Simulator) -> None:
    n0 = sim.induced_charges()
    assert set(n0) == {"D1", "D2", "SD"}
    assert sim.gate_turn_on("PB") == pytest.approx(sim._turn_on("PB"))
    readings = sim.reading_count
    sim.induced_charges()
    assert sim.reading_count == readings
    with pytest.raises(KeyError):
        sim.gate_turn_on("NOPE")


def test_occupations_at_is_hypothetical_and_side_effect_free(sim: Simulator) -> None:
    before = sim.occupations()
    readings, state = sim.reading_count, dict(sim.state)
    hypothetical = sim.occupations_at({"PA1": -1.0, "PA2": -1.0})
    assert hypothetical["D1"] > before["D1"]  # holes accumulate at negative voltage
    assert sim.occupations() == before
    assert sim.reading_count == readings and sim.state == state
    with pytest.raises(KeyError):
        sim.occupations_at({"NOPE": 0.0})
