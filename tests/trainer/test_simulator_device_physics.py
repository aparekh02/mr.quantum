"""Sprint 2 simulator physics, checked against the configured capacitances."""

from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError
from scipy.signal import find_peaks

from stanza.device import Device
from stanza.drivers.simulator import Simulator
from stanza.models import DeviceConfig
from stanza.utils import device_from_config, device_from_yaml
from tests.trainer.conftest import DQD_YAML

SIDE_A = ["RA1", "BA0", "PA1", "BA1", "PA2", "BA2", "RA2"]
SIDE_B = ["RB1", "BB0", "PB", "BB1", "RB2"]
OPEN = -1.7  # every turn-on is complete to better than 1e-5 here


def _device(config: dict[str, Any]) -> Device:
    return device_from_config(DeviceConfig.model_validate(config))


def _sim_cfg(config: dict[str, Any]) -> dict[str, Any]:
    sim: dict[str, Any] = config["instruments"][0]["simulation"]
    return sim


def _simulator(device: Device) -> Simulator:
    sim = device.control_instrument
    assert isinstance(sim, Simulator)
    return sim


def _sensor_ready(device: Device, barrier: float = -0.74) -> None:
    """Sensor side accumulated, sensor barriers partly pinched: a blockaded dot."""
    device.jump(
        {
            **dict.fromkeys(SIDE_B, OPEN),
            "BB0": barrier,
            "BB1": barrier,
            "IN_B": 0.001,
        }
    )


def _sensor_sweep(device: Device, v: np.ndarray) -> np.ndarray:
    _, currents = device.sweep_1d("PB", list(v), "OUT_B")
    return np.array(currents)


def _peak_positions(v: np.ndarray, i: np.ndarray) -> np.ndarray:
    idx, _ = find_peaks(i, prominence=0.3 * i.max())
    return v[idx]


@pytest.fixture
def quiet(quiet_dqd_dict: dict[str, Any]) -> Device:
    return _device(quiet_dqd_dict)


# --- loading ------------------------------------------------------------------


def test_dqd_device_loads_from_yaml() -> None:
    device = device_from_yaml(DQD_YAML)
    sim = _simulator(device)
    assert set(sim.dots) == {"D1", "D2", "SD"}
    assert [c.name for c in sim.conduction_channels] == ["A", "B"]


def test_sides_are_independent_channels(quiet: Device) -> None:
    quiet.jump({**dict.fromkeys(SIDE_A + SIDE_B, OPEN), "IN_A": 0.001})
    assert quiet.measure("OUT_A") > 1e-9
    assert quiet.measure("OUT_B") == 0.0  # side B has no bias


# --- Coulomb blockade on the sensor ------------------------------------------


def test_sensor_peak_spacing_is_charging_energy_over_lever_arm(
    quiet: Device, quiet_dqd_dict: dict[str, Any]
) -> None:
    sd = _sim_cfg(quiet_dqd_dict)["dots"]["SD"]
    expected = sd["charging_energy"] / sd["lever_arms"]["PB"]  # 20 mV
    _sensor_ready(quiet)
    v = np.linspace(-0.90, -0.70, 2001)
    peaks = _peak_positions(v, _sensor_sweep(quiet, v))
    assert len(peaks) >= 6
    # Barrier voltages are constant during the sweep, so spacing is exact.
    assert np.diff(peaks) == pytest.approx(expected, rel=0.02)


def test_sensor_peak_count_matches_induced_charge_range(
    quiet: Device, quiet_dqd_dict: dict[str, Any]
) -> None:
    sd = _sim_cfg(quiet_dqd_dict)["dots"]["SD"]
    _sensor_ready(quiet)
    v = np.linspace(-0.90, -0.70, 2001)
    peaks = _peak_positions(v, _sensor_sweep(quiet, v))
    induced = 0.20 * sd["lever_arms"]["PB"] / sd["charging_energy"]  # 10 charges
    assert abs(len(peaks) - induced) <= 1


def test_open_dot_shows_no_blockade(quiet: Device) -> None:
    _sensor_ready(quiet, barrier=OPEN)
    quiet.jump({"PB": OPEN})
    v = np.linspace(-1.80, -1.60, 801)
    i = _sensor_sweep(quiet, v)
    # Fully open: current varies by well under 1% across many "peak" spacings.
    assert np.ptp(i) / i.mean() < 0.01


def test_blockade_strengthens_as_barriers_pinch(quiet: Device) -> None:
    contrasts = []
    for barrier in (-0.90, -0.78, -0.72):
        _sensor_ready(quiet, barrier=barrier)
        i = _sensor_sweep(quiet, np.linspace(-0.90, -0.80, 401))
        contrasts.append((i.max() - i.min()) / i.max())
    assert contrasts[0] < contrasts[1] < contrasts[2]


# --- cross-capacitance -----------------------------------------------------------


def test_control_plunger_shifts_sensor_peak_by_lever_arm_ratio(
    quiet: Device, quiet_dqd_dict: dict[str, Any]
) -> None:
    arms = _sim_cfg(quiet_dqd_dict)["dots"]["SD"]["lever_arms"]
    _sensor_ready(quiet)
    v = np.linspace(-0.87, -0.83, 4001)
    # Side A at 0 V and above: both control dots empty, so only direct capacitive
    # cross-talk acts. Keep the shift below one peak spacing to track one peak.
    quiet.jump({"PA1": 0.0})
    before = _peak_positions(v, _sensor_sweep(quiet, v))
    quiet.jump({"PA1": 0.05})
    after = _peak_positions(v, _sensor_sweep(quiet, v))
    shift = after[np.argmin(np.abs(after - before[1]))] - before[1]
    # Holes: making PA1 more positive pushes the sensor peak more negative.
    predicted = -arms["PA1"] / arms["PB"] * 0.05
    assert shift == pytest.approx(predicted, abs=2e-5)


def test_extra_charge_on_control_dot_steps_sensor_by_mutual_energy(
    quiet: Device, quiet_dqd_dict: dict[str, Any]
) -> None:
    """Charge sensing: one more hole on D1 steps the sensor peak by -Em/alpha_PB.

    On either side of the D1 transition the sensor peak drifts linearly with PA1
    (direct cross-capacitance). Extrapolating both plateaus to the transition
    isolates the step caused by the extra charge.
    """
    cfg = _sim_cfg(quiet_dqd_dict)
    em = next(m["energy"] for m in cfg["mutual"] if set(m["dots"]) == {"SD", "D1"})
    arms = cfg["dots"]["SD"]["lever_arms"]
    sim = _simulator(quiet)
    quiet.jump({"PA2": 0.3})  # keep D2 empty
    _sensor_ready(quiet)
    quiet.jump({"PB": -0.85})  # the sensor's own charge also shifts D1
    edge = sim.transition_voltage("D1", "PA1", n=0)
    pa1 = edge + np.linspace(0.015, -0.015, 31)  # empty -> one hole
    v = np.linspace(-0.87, -0.83, 4001)
    positions, last = [], None
    for x in pa1:
        quiet.jump({"PA1": float(x)})
        found = _peak_positions(v, _sensor_sweep(quiet, v))
        last = found[0] if last is None else found[np.argmin(np.abs(found - last))]
        positions.append(last)
    pos = np.array(positions)
    empty, filled = pa1 > edge + 0.006, pa1 < edge - 0.006
    fit_empty = np.polyfit(pa1[empty], pos[empty], 1)
    fit_filled = np.polyfit(pa1[filled], pos[filled], 1)
    # Plateau slope is the direct cross-capacitance ratio.
    assert fit_empty[0] == pytest.approx(-arms["PA1"] / arms["PB"], rel=0.02)
    step = np.polyval(fit_filled, edge) - np.polyval(fit_empty, edge)
    assert step == pytest.approx(-em / arms["PB"], rel=0.05)


# --- double dot ------------------------------------------------------------------


def _charge_map(device: Device, n: int = 61) -> np.ndarray:
    sim = _simulator(device)
    x = np.linspace(-0.66, -0.56, n)
    states = np.empty((n, n), dtype=np.int64)
    for i, a in enumerate(x):
        for j, b in enumerate(x + 0.0007):  # avoid exact degeneracies
            device.jump({"PA1": a, "PA2": b})
            occ = sim.occupations()
            states[i, j] = round(occ["D1"]) * 100 + round(occ["D2"])
    return states


def _max_states_at_vertex(states: np.ndarray) -> int:
    return max(
        len({states[i, j], states[i + 1, j], states[i, j + 1], states[i + 1, j + 1]})
        for i in range(states.shape[0] - 1)
        for j in range(states.shape[1] - 1)
    )


def test_double_dot_charge_map_is_a_honeycomb(quiet: Device) -> None:
    states = _charge_map(quiet)
    assert len(np.unique(states)) >= 6
    assert _max_states_at_vertex(states) == 3


def test_without_mutual_charging_the_map_is_a_square_grid(
    quiet_dqd_dict: dict[str, Any],
) -> None:
    for m in _sim_cfg(quiet_dqd_dict)["mutual"]:
        if set(m["dots"]) == {"D1", "D2"}:
            m["energy"] = 0.0
    states = _charge_map(_device(quiet_dqd_dict))
    assert _max_states_at_vertex(states) == 4


def _transport_map(device: Device, inner: float, n: int = 48) -> np.ndarray:
    device.jump(
        {
            **dict.fromkeys(SIDE_A, OPEN),
            "BA0": -0.9,
            "BA2": -0.9,
            "BA1": inner,
            "IN_A": 0.001,
        }
    )
    x = np.linspace(-0.66, -0.58, n)
    image = np.empty((n, n))
    for i, b in enumerate(x):
        for j, a in enumerate(x):
            device.jump({"PA1": a, "PA2": b})
            image[i, j] = device.measure("OUT_A")
    return image


def test_double_dot_transport_shows_two_line_families(quiet: Device) -> None:
    from trainer.models.analysis import classify_double_dot

    is_dqd, _ = classify_double_dot(_transport_map(quiet, inner=-0.75))
    assert is_dqd


def test_open_inner_barrier_merges_into_a_single_dot(quiet: Device) -> None:
    from trainer.models.analysis import classify_double_dot

    is_dqd, _ = classify_double_dot(_transport_map(quiet, inner=OPEN))
    assert not is_dqd


# --- leakage -----------------------------------------------------------------------


def test_gates_do_not_leak_unless_configured(quiet: Device) -> None:
    quiet.jump(dict.fromkeys(SIDE_A + SIDE_B, -2.0))
    assert quiet.measure(SIDE_A + SIDE_B) == [0.0] * 12


def test_configured_leak_appears_only_on_its_gates(
    quiet_dqd_dict: dict[str, Any],
) -> None:
    _sim_cfg(quiet_dqd_dict)["leakage"] = [
        {"gates": ["BA0", "PA1"], "resistance": 1.0e8, "onset": 0.5}
    ]
    device = _device(quiet_dqd_dict)
    device.jump({"BA0": -2.0, "PA1": 0.0})
    currents = dict(zip(SIDE_A + SIDE_B, device.measure(SIDE_A + SIDE_B), strict=True))
    assert currents["BA0"] == pytest.approx(-1.5 / 1e8)
    assert currents["PA1"] == pytest.approx(1.5 / 1e8)
    assert all(v == 0.0 for k, v in currents.items() if k not in {"BA0", "PA1"})


def test_leak_to_ground(quiet_dqd_dict: dict[str, Any]) -> None:
    _sim_cfg(quiet_dqd_dict)["leakage"] = [
        {"gates": ["PB", "ground"], "resistance": 1.0e9, "onset": 0.0}
    ]
    device = _device(quiet_dqd_dict)
    device.jump({"PB": -1.0})
    assert device.measure("PB") == pytest.approx(-1e-9)


# --- time and charge noise ----------------------------------------------------------


def test_each_reading_advances_the_simulated_clock(quiet: Device) -> None:
    sim = _simulator(quiet)
    start = sim.clock.now()
    for _ in range(10):
        quiet.measure("OUT_B")
    assert sim.clock.now() - start == pytest.approx(10 * 0.001)


def test_charge_noise_makes_flank_current_fluctuate_in_time(
    dqd_dict: dict[str, Any],
) -> None:
    _sim_cfg(dqd_dict)["noise_std"] = 0.0  # isolate charge noise
    device = _device(dqd_dict)
    _sensor_ready(device)
    v = np.linspace(-0.87, -0.83, 801)
    i = _sensor_sweep(device, v)
    flank = v[int(np.argmax(np.gradient(i)))]
    device.jump({"PB": float(flank)})
    readings = np.array([device.measure("OUT_B") for _ in range(400)])
    assert readings.std() > 0.0
    # Correlated in time (tau = 0.5 s >> 1 ms per reading), unlike white noise.
    assert np.corrcoef(readings[:-1], readings[1:])[0, 1] > 0.9


def test_charge_noise_is_deterministic(dqd_dict: dict[str, Any]) -> None:
    a, b = _device(dqd_dict), _device(dqd_dict)
    for d in (a, b):
        _sensor_ready(d)
        d.jump({"PB": -0.85})
    assert [a.measure("OUT_B") for _ in range(50)] == [
        b.measure("OUT_B") for _ in range(50)
    ]


# --- config validation ----------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda s: s["channels"][0]["segments"].append("XX"), "XX"),
        (lambda s: s["dots"]["D1"].update(plunger="PB"), "PB"),
        (lambda s: s["channels"][1]["dots"].append("D1"), "D1"),
        (lambda s: s["dots"]["D2"].update(barriers=["BA2", "RA2"]), "share"),
        (lambda s: s["mutual"].append({"dots": ["D1", "ZZ"], "energy": 1e-4}), "ZZ"),
        (lambda s: s["mutual"].append({"dots": ["D1", "D1"], "energy": 1e-4}), "D1"),
        (
            lambda s: s.update(
                leakage=[{"gates": ["BA0", "QQ"], "resistance": 1e8, "onset": 0.0}]
            ),
            "QQ",
        ),
        (lambda s: s["channels"][0].update(source="OUT_A"), "SOURCE"),
        (lambda s: s["channels"][1].update(drain="OUT_A"), "OUT_A"),
        (lambda s: s["dots"]["SD"]["lever_arms"].update(NOPE=0.1), "NOPE"),
        (lambda s: s["dots"]["SD"].update(charging_energy=0.0), "charging_energy"),
        (lambda s: s.update(temperature=0.0), "temperature"),
        (lambda s: s["channels"][0].update(dots=["D1", "D2", "SD"]), "at most two"),
    ],
)
def test_bad_dqd_config_rejected(
    dqd_dict: dict[str, Any], mutate: Any, match: str
) -> None:
    mutate(_sim_cfg(dqd_dict))
    with pytest.raises((ValidationError, ValueError), match=match):
        _device(dqd_dict)


def test_dots_require_channels(single_channel_dict: dict[str, Any]) -> None:
    single_channel_dict["instruments"][0]["simulation"]["dots"] = {
        "X": {
            "charging_energy": 1e-3,
            "plunger": "P1",
            "barriers": [],
            "lever_arms": {},
        }
    }
    with pytest.raises(ValidationError, match="channels"):
        _device(single_channel_dict)


def test_transition_voltage_validates_inputs(quiet: Device) -> None:
    sim = _simulator(quiet)
    with pytest.raises(KeyError):
        sim.transition_voltage("NOPE", "PA1", n=0)
    with pytest.raises(ValueError, match="lever arm"):
        sim.transition_voltage("D1", "RB1", n=0)
