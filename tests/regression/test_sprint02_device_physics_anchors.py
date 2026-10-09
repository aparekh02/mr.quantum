"""Regression anchors (Sprint 2): upstream routines on the simulated hole device.

The six routines PLAN.md names run unmodified, through upstream's RoutineRunner,
against trainer/devices/dqd_with_sensor.yaml, in the order a researcher would run
them. Each test checks its routine's output against the simulator's ground truth,
not just that it returned.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from trainer.lab import SimulatedLab
from trainer.workflows import DQD_WITH_SENSOR_TUNEUP, run_steps

DEVICE = (
    Path(__file__).resolve().parents[2] / "trainer" / "devices" / "dqd_with_sensor.yaml"
)
SIDE_A = ["RA1", "BA0", "PA1", "BA1", "PA2", "BA2", "RA2"]


@pytest.fixture(scope="module")
def tuned(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[SimulatedLab, dict[str, Any]]:
    """Run the whole tune-up once; keep each step's result and the voltages it left."""
    lab = SimulatedLab.from_yaml(DEVICE, base_dir=tmp_path_factory.mktemp("lab"))
    results: dict[str, Any] = {}
    for step in DQD_WITH_SENSOR_TUNEUP:
        results.update(run_steps(lab, [step]))
        results[f"{step.label}@state"] = dict(lab.simulator.state)
    return lab, results


def _sensor_charge_offset(
    lab: SimulatedLab, state: dict[str, float], park: dict[str, float]
) -> float:
    """Fractional induced charge of the sensor dot at a park point (0.5 = peak),
    with every other gate where the routine left it."""
    lab.device.jump({**state, **park})
    shifted, _, _ = lab.simulator._induced_charges()
    return float(shifted["SD"] % 1.0)


def test_leakage_test_reports_full_safe_range_on_a_clean_device(
    tuned: tuple[SimulatedLab, dict[str, Any]],
) -> None:
    _, results = tuned
    for side in ("side_A", "side_B"):
        bounds = results[f"{side}/leakage_test"]
        assert bounds["max_safe_voltage_bound"] == pytest.approx(0.3)
        assert bounds["min_safe_voltage_bound"] == pytest.approx(-2.0)


def test_reservoir_characterization_finds_each_reservoir_turn_on(
    tuned: tuple[SimulatedLab, dict[str, Any]],
) -> None:
    lab, results = tuned
    for side, reservoirs in (("side_A", ["RA1", "RA2"]), ("side_B", ["RB1", "RB2"])):
        found = results[f"{side}/reservoir_characterization"][
            "reservoir_characterization"
        ]
        assert set(found) == set(reservoirs)
        for name in reservoirs:
            gate = lab.simulator.turn_on[name]
            r = found[name]
            # Holes: saturation (open) is more negative than cutoff (closed), and the
            # configured threshold lies between them.
            assert r["saturation_voltage"] < gate.v_threshold < r["cutoff_voltage"]


def test_find_sensor_peak_parks_on_a_real_coulomb_peak(
    tuned: tuple[SimulatedLab, dict[str, Any]],
) -> None:
    lab, results = tuned
    r = results["find_sensor_peak"]
    park = {**r["sensor_park_point"], "PB": r["best_peak_voltage"]}
    state = results["find_sensor_peak@state"]
    # A Coulomb peak is a charge degeneracy: induced charge n + 1/2.
    assert _sensor_charge_offset(lab, state, park) == pytest.approx(0.5, abs=0.08)
    spacing = lab.simulator.dots["SD"].charging_energy / 0.08
    assert r["next_peak_voltage"] - r["prev_peak_voltage"] == pytest.approx(
        2 * spacing, rel=0.1
    )


def test_find_stable_sensor_peak_leaves_sensor_on_a_steep_flank(
    tuned: tuple[SimulatedLab, dict[str, Any]],
) -> None:
    lab, results = tuned
    r = results["find_stable_sensor_peak"]
    assert r["best_peak_max_gradient_voltage"] != r["best_peak_voltage"]
    offset = _sensor_charge_offset(
        lab, results["find_stable_sensor_peak@state"], dict(r["sensor_park_point"])
    )
    # The steepest point of a thermal sech^2(mu / 2kT) peak is at mu = 1.317 kT,
    # with kT broadened by how open the sensor dot is.
    sim = lab.simulator
    openness = sim._turn_on("PB") * sim._turn_on("BB0") * sim._turn_on("BB1")
    kt = sim.settings.temperature + sim.settings.lifetime_broadening * openness
    expected = 1.317 * kt / sim.dots["SD"].charging_energy
    assert abs(offset - 0.5) == pytest.approx(expected, rel=0.3)


def test_run_compensation_recovers_the_cross_capacitance_ratios(
    tuned: tuple[SimulatedLab, dict[str, Any]],
) -> None:
    lab, results = tuned
    gradients = results["run_compensation"]["compensation_gradients"]
    arms = lab.simulator.dots["SD"].lever_arms
    for gate in ("PA1", "PA2", "BA0", "BA1", "BA2"):
        predicted = -arms.get(gate, 0.0) / arms["PB"]
        assert gradients[gate] == pytest.approx(predicted, abs=0.012), gate


def test_run_dqd_search_finds_a_genuine_double_dot(
    tuned: tuple[SimulatedLab, dict[str, Any]],
) -> None:
    lab, results = tuned
    sweeps = results["run_dqd_search"]["run_dqd_search"]
    found = [sq for sw in sweeps for sq in sw["dqd_squares"]]
    assert found, "no double dot found"
    best = found[0]
    voltages = np.array(best["high_res_csd_voltages"]).reshape(48, 48, len(SIDE_A))
    sim = lab.simulator
    lab.device.jump(results["run_dqd_search@state"])
    occupations = []
    for i, j in ((0, 0), (0, -1), (-1, 0), (-1, -1)):
        lab.device.jump(dict(zip(SIDE_A, voltages[i, j].tolist(), strict=True)))
        occupations.append(sim.occupations())
    # Inside the square both dots change charge: two separate dots, not one.
    assert len({round(o["D1"]) for o in occupations}) > 1
    assert len({round(o["D2"]) for o in occupations}) > 1
    # The inner barrier really is pinched enough to keep the dots apart.
    inner = sim._turn_on("BA1") ** 4
    assert inner < 0.5
