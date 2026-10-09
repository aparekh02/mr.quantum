"""The simulator driver loads through upstream's own path and behaves like hardware."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

from stanza.base.protocols import ControlInstrument, MeasurementInstrument
from stanza.base.registry import load_driver_class, validate_driver_protocols
from stanza.device import Device
from stanza.exceptions import DeviceError
from stanza.models import DeviceConfig, InstrumentType
from stanza.utils import device_from_config, device_from_yaml
from tests.trainer.conftest import SINGLE_CHANNEL_YAML
from trainer.physics.pinchoff import (
    ELECTRON,
    GateTurnOn,
    channel_current,
    gate_conductance,
    series_conductance,
)

GATES = ["R1", "B1", "P1", "B2", "R2"]


def _device(config: dict[str, Any]) -> Device:
    return device_from_config(DeviceConfig.model_validate(config))


def _sim(config: dict[str, Any]) -> dict[str, Any]:
    sim: dict[str, Any] = config["instruments"][0]["simulation"]
    return sim


def _expected_current(config: dict[str, Any], voltages: dict[str, float]) -> float:
    """Independent reference: the physics functions composed by hand."""
    sim = _sim(config)
    gs = [
        gate_conductance(voltages[g], GateTurnOn(**sim["gates"][g]), ELECTRON)
        for g in GATES
    ]
    g_total = series_conductance(gs, sim["series_resistance"])
    return channel_current(voltages.get("S", 0.0), g_total)


@pytest.fixture
def device() -> Device:
    return device_from_yaml(SINGLE_CHANNEL_YAML)


# --- loading through upstream ----------------------------------------------


def test_load_driver_class_resolves_simulator() -> None:
    cls = load_driver_class("simulator")
    assert cls.__name__ == "Simulator"
    assert cls.__module__ == "stanza.drivers.simulator"


@pytest.mark.parametrize(
    "instrument_type",
    [InstrumentType.GENERAL, InstrumentType.CONTROL, InstrumentType.MEASUREMENT],
)
def test_validate_driver_protocols_passes(instrument_type: InstrumentType) -> None:
    validate_driver_protocols(load_driver_class("simulator"), instrument_type)


def test_device_from_yaml_uses_one_simulator_for_both_roles(device: Device) -> None:
    assert device.control_instrument is device.measurement_instrument
    assert isinstance(device.control_instrument, ControlInstrument)
    assert isinstance(device.measurement_instrument, MeasurementInstrument)
    assert device.is_configured()


def test_instrument_config_exposes_breakout_line(device: Device) -> None:
    assert device.control_instrument is not None
    assert device.control_instrument.instrument_config.breakout_line is None


def test_breakout_line_is_passed_through(single_channel_dict: dict[str, Any]) -> None:
    single_channel_dict["instruments"][0]["breakout_line"] = 3
    dev = _device(single_channel_dict)
    assert dev.control_instrument is not None
    assert dev.control_instrument.instrument_config.breakout_line == 3


# --- control --------------------------------------------------------------------


def test_voltages_start_at_zero(device: Device) -> None:
    assert device.check(GATES + ["S"]) == [0.0] * 6


def test_set_and_get_voltage(device: Device) -> None:
    device.jump({"P1": 0.7, "S": 0.001})
    assert device.check("P1") == 0.7
    assert device.check("S") == 0.001


def test_slew_rate_comes_from_config(device: Device) -> None:
    assert device.control_instrument is not None
    assert device.control_instrument.get_slew_rate("P1") == 1000.0


@pytest.mark.parametrize("voltage", [-2.0, 2.0])
def test_voltage_at_bound_is_accepted(device: Device, voltage: float) -> None:
    device.jump({"P1": voltage})
    assert device.check("P1") == voltage


@pytest.mark.parametrize("voltage", [-2.0001, 2.0001, 10.0])
def test_voltage_outside_bounds_rejected_and_unchanged(
    device: Device, voltage: float
) -> None:
    device.jump({"P1": 0.3})
    with pytest.raises(DeviceError, match="Invalid value"):
        device.jump({"P1": voltage})
    assert device.check("P1") == 0.3


def test_contact_bounds_enforced(device: Device) -> None:
    with pytest.raises(DeviceError):
        device.jump({"S": 0.02})


def test_unknown_channel_raises(device: Device) -> None:
    assert device.control_instrument is not None
    with pytest.raises(KeyError):
        device.control_instrument.set_voltage("nope", 0.1)


# --- measurement ------------------------------------------------------------


def test_no_bias_gives_noise_only(device: Device) -> None:
    device.jump(dict.fromkeys(GATES, 1.5))
    currents = np.array([device.measure("D") for _ in range(500)])
    assert abs(currents.mean()) < 3e-12
    assert currents.std() == pytest.approx(1e-11, rel=0.15)


def test_pinched_channel_gives_noise_only(device: Device) -> None:
    device.jump({"S": 0.001})  # all gates at 0 V: depleted
    currents = np.array([device.measure("D") for _ in range(500)])
    assert abs(currents.mean()) < 3e-12


def test_open_channel_current_matches_physics(
    single_channel_dict: dict[str, Any],
) -> None:
    _sim(single_channel_dict)["noise_std"] = 0.0
    dev = _device(single_channel_dict)
    voltages = {**dict.fromkeys(GATES, 1.5), "S": 0.001}
    dev.jump(voltages)
    expected = _expected_current(single_channel_dict, voltages)
    assert dev.measure("D") == pytest.approx(expected, rel=1e-12)
    # Fully open: limited by contacts and g_max of each segment, a few nA.
    assert 1e-9 < expected < 1e-7


def test_current_is_negative_at_source_side(
    single_channel_dict: dict[str, Any],
) -> None:
    single_channel_dict["contacts"]["S"]["measure_channel"] = 7
    _sim(single_channel_dict)["noise_std"] = 0.0
    dev = _device(single_channel_dict)
    dev.jump({**dict.fromkeys(GATES, 1.5), "S": 0.001})
    assert dev.measure("S") == pytest.approx(-dev.measure("D"), rel=1e-12)


def test_gate_currents_are_noise_only_without_leakage(device: Device) -> None:
    device.jump({**dict.fromkeys(GATES, 1.5), "S": 0.001})
    readings = np.array([device.measure("P1") for _ in range(200)])
    assert abs(readings.mean()) < 3e-12


def test_measure_list_returns_list(device: Device) -> None:
    out = device.measure(["D", "P1", "B1"])
    assert isinstance(out, list)
    assert len(out) == 3


def test_measure_pad_without_measure_channel_raises(device: Device) -> None:
    with pytest.raises(DeviceError, match="no measure channel"):
        device.measure("S")


def test_any_single_pinched_gate_blocks_channel(
    single_channel_dict: dict[str, Any],
) -> None:
    _sim(single_channel_dict)["noise_std"] = 0.0
    dev = _device(single_channel_dict)
    dev.jump({**dict.fromkeys(GATES, 1.5), "S": 0.001})
    open_current = dev.measure("D")
    for gate in GATES:
        dev.jump({gate: -1.0})
        assert dev.measure("D") < 1e-6 * open_current, gate
        dev.jump({gate: 1.5})


# --- sweeps: shapes, monotonicity, determinism, golden ----------------------


def test_sweep_1d_shapes(device: Device) -> None:
    voltages = list(np.linspace(0.0, 1.5, 31))
    v_out, i_out = device.sweep_1d("P1", voltages, "D")
    assert len(v_out) == 31
    assert len(i_out) == 31
    assert v_out == pytest.approx(voltages)


def test_sweep_nd_shapes(device: Device) -> None:
    steps = [[v, v] for v in np.linspace(0.0, 1.0, 11)]
    v_out, i_out = device.sweep_nd(["B1", "B2"], steps, "D")
    assert np.array(v_out).shape == (11, 2)
    assert len(i_out) == 11


def test_plunger_turn_on_is_monotonic_without_noise(
    single_channel_dict: dict[str, Any],
) -> None:
    _sim(single_channel_dict)["noise_std"] = 0.0
    dev = _device(single_channel_dict)
    dev.jump({**dict.fromkeys(GATES, 1.5), "S": 0.001})
    _, currents = dev.sweep_1d("P1", list(np.linspace(-0.5, 1.5, 201)), "D")
    assert np.all(np.diff(currents) >= 0)
    assert currents[0] < 1e-3 * currents[-1]


def test_same_seed_same_data(single_channel_dict: dict[str, Any]) -> None:
    sweeps = []
    for _ in range(2):
        dev = _device(single_channel_dict)
        dev.jump({**dict.fromkeys(GATES, 1.5), "S": 0.001})
        sweeps.append(dev.sweep_1d("P1", list(np.linspace(0, 1, 21)), "D")[1])
    assert sweeps[0] == sweeps[1]


def test_different_seed_different_noise(single_channel_dict: dict[str, Any]) -> None:
    a = _device(single_channel_dict)
    _sim(single_channel_dict)["seed"] = 4321
    b = _device(single_channel_dict)
    assert [a.measure("D") for _ in range(5)] != [b.measure("D") for _ in range(5)]


def test_golden_sweep_at_seed(single_channel_dict: dict[str, Any]) -> None:
    dev = _device(single_channel_dict)
    bias = {**dict.fromkeys(GATES, 1.5), "S": 0.001}
    dev.jump(bias)
    plunger = list(np.linspace(0.3, 0.7, 5))
    _, currents = dev.sweep_1d("P1", plunger, "D")

    # Golden: noiseless physics + the seed's own normal draws, one per reading.
    normals = np.random.default_rng(1234).standard_normal(5)
    expected = [
        _expected_current(single_channel_dict, {**bias, "P1": v}) + 1e-11 * n
        for v, n in zip(plunger, normals, strict=True)
    ]
    assert currents == pytest.approx(expected, rel=1e-12, abs=0)


# --- config validation at the boundary -------------------------------------


def test_seed_is_required(single_channel_dict: dict[str, Any]) -> None:
    del _sim(single_channel_dict)["seed"]
    with pytest.raises(ValidationError, match="seed"):
        _device(single_channel_dict)


def test_simulation_block_is_required(single_channel_dict: dict[str, Any]) -> None:
    del single_channel_dict["instruments"][0]["simulation"]
    with pytest.raises(ValidationError, match="simulation"):
        _device(single_channel_dict)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("noise_std", -1e-12),
        ("series_resistance", -1.0),
        ("carrier", "positron"),
        ("seed", -1),
    ],
)
def test_bad_simulation_values_rejected(
    single_channel_dict: dict[str, Any], field: str, value: Any
) -> None:
    _sim(single_channel_dict)[field] = value
    with pytest.raises(ValidationError):
        _device(single_channel_dict)


def test_bad_gate_width_rejected(single_channel_dict: dict[str, Any]) -> None:
    _sim(single_channel_dict)["gates"]["P1"]["width"] = 0.0
    with pytest.raises(ValidationError, match="width"):
        _device(single_channel_dict)


def test_missing_gate_physics_rejected(single_channel_dict: dict[str, Any]) -> None:
    del _sim(single_channel_dict)["gates"]["B2"]
    with pytest.raises(ValidationError, match="B2"):
        _device(single_channel_dict)


def test_unknown_gate_physics_rejected(single_channel_dict: dict[str, Any]) -> None:
    _sim(single_channel_dict)["gates"]["X9"] = {
        "v_threshold": 0.5,
        "width": 0.05,
        "g_max": 1e-5,
    }
    with pytest.raises(ValidationError, match="X9"):
        _device(single_channel_dict)


def test_screen_gates_need_no_turn_on(single_channel_dict: dict[str, Any]) -> None:
    single_channel_dict["gates"]["SC"] = {
        "type": "SCREEN",
        "control_channel": 9,
        "v_lower_bound": -1.0,
        "v_upper_bound": 1.0,
    }
    dev = _device(single_channel_dict)
    dev.jump({"SC": 0.5})
    assert dev.check("SC") == 0.5


def test_hole_device_conducts_at_negative_voltage(
    single_channel_dict: dict[str, Any], tmp_path: Path
) -> None:
    sim = _sim(single_channel_dict)
    sim["carrier"] = "hole"
    sim["noise_std"] = 0.0
    for params in sim["gates"].values():
        params["v_threshold"] = -params["v_threshold"]
    path = tmp_path / "hole.yaml"
    path.write_text(yaml.safe_dump(single_channel_dict))
    dev = device_from_yaml(path)
    dev.jump({**dict.fromkeys(GATES, -1.5), "S": 0.001})
    on = dev.measure("D")
    dev.jump(dict.fromkeys(GATES, 1.5))
    off = dev.measure("D")
    assert on > 1e-9
    assert off < 1e-6 * on


def test_requires_a_source_and_drain(single_channel_dict: dict[str, Any]) -> None:
    del single_channel_dict["contacts"]["S"]
    with pytest.raises(ValueError, match="SOURCE"):
        _device(single_channel_dict)


# --- remaining driver surface -------------------------------------------------


def test_simulation_settings_validate_standalone(
    single_channel_dict: dict[str, Any],
) -> None:
    from stanza.drivers.simulator import SimulationSettings

    settings = SimulationSettings.model_validate(_sim(single_channel_dict))
    assert settings.seed == 1234
    assert set(settings.gates) == set(GATES)


def test_set_slew_rate_round_trips(device: Device) -> None:
    sim = device.control_instrument
    assert sim is not None
    sim.set_slew_rate("P1", 5.0)
    assert sim.get_slew_rate("P1") == 5.0


def test_slew_rate_above_channel_limit_rejected(
    single_channel_dict: dict[str, Any],
) -> None:
    # Upstream ControlChannel limits slew rate to [0.001, 1000] V/s.
    single_channel_dict["instruments"][0]["slew_rate"] = 2000.0
    with pytest.raises(ValueError, match="slew_rate"):
        _device(single_channel_dict)


def test_state_reports_set_voltages(device: Device) -> None:
    device.jump({"P1": 0.4, "S": 0.001})
    sim = device.control_instrument
    assert sim is not None
    state = sim.state
    assert state["P1"] == 0.4
    assert state["S"] == 0.001
    assert "D" not in state  # drain has no control channel
