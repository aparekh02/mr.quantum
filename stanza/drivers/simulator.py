"""Physics simulator driver: a GENERAL instrument backed by trainer.physics models.

Loaded like any other Stanza driver (``driver: simulator`` in device YAML). One
instance is both the control and the measurement instrument, because computing a
current needs the gate voltages. Physics parameters come from the ``simulation``
block of the instrument entry, validated here at the boundary. This module
composes the pure functions in ``trainer.physics``; it holds no physics itself.

Example instrument entry::

    - name: simulator
      type: GENERAL
      driver: simulator
      ip_addr: simulated
      slew_rate: 1000.0
      measurement_duration: 0.001
      sample_time: 0.0001
      simulation:
        seed: 1234
        carrier: electron
        noise_std: 1.0e-11
        series_resistance: 1.0e4
        gates:
          P1: {v_threshold: 0.45, width: 0.05, g_max: 5.0e-5}
"""

from __future__ import annotations

from functools import partial
from typing import Any, Literal, overload

import numpy as np
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    PositiveFloat,
    ValidationInfo,
    model_validator,
)

from stanza.base.channels import ChannelConfig, ControlChannel, MeasurementChannel
from stanza.base.instruments import GeneralInstrument
from stanza.models import ContactType, GateType, GeneralInstrumentConfig, PadType
from trainer.physics.pinchoff import (
    ELECTRON,
    HOLE,
    GateTurnOn,
    channel_current,
    gate_conductance,
    noisy,
    series_conductance,
)


class TurnOnSettings(BaseModel):
    """Pinch-off parameters for the channel segment under one gate."""

    model_config = ConfigDict(extra="forbid")

    v_threshold: float
    width: PositiveFloat
    g_max: NonNegativeFloat


class SimulationSettings(BaseModel):
    """The ``simulation`` block of a simulator instrument entry."""

    model_config = ConfigDict(extra="forbid")

    seed: int = Field(ge=0)
    carrier: Literal["electron", "hole"]
    noise_std: NonNegativeFloat
    series_resistance: NonNegativeFloat
    gates: dict[str, TurnOnSettings]

    @model_validator(mode="after")
    def gates_match_device(self, info: ValidationInfo) -> SimulationSettings:
        """Every channel gate needs turn-on parameters, and only those gates."""
        context = info.context or {}
        expected: set[str] | None = context.get("channel_gates")
        if expected is None:
            return self
        missing = sorted(expected - self.gates.keys())
        unknown = sorted(self.gates.keys() - expected)
        if missing:
            raise ValueError(f"simulation.gates is missing turn-on for: {missing}")
        if unknown:
            raise ValueError(
                f"simulation.gates names gates not in the channel: {unknown}"
            )
        return self


class _SimulatorExtras(BaseModel):
    simulation: SimulationSettings


class Simulator(GeneralInstrument):
    """Simulated quantum-dot device exposed as a Stanza GENERAL instrument."""

    def __init__(
        self,
        instrument_config: GeneralInstrumentConfig,
        channel_configs: dict[str, ChannelConfig],
    ) -> None:
        super().__init__(instrument_config)
        self.channel_configs = channel_configs

        channel_gates = {
            name
            for name, cfg in channel_configs.items()
            if cfg.pad_type == PadType.GATE and cfg.electrode_type != GateType.SCREEN
        }
        extras = _SimulatorExtras.model_validate(
            instrument_config.model_extra or {},
            context={"channel_gates": channel_gates},
        )
        self.settings = extras.simulation
        self.polarity = ELECTRON if self.settings.carrier == "electron" else HOLE
        self.turn_on = {
            name: GateTurnOn(s.v_threshold, s.width, s.g_max)
            for name, s in self.settings.gates.items()
        }
        self.source = self._single_contact(ContactType.SOURCE)
        self.drain = self._single_contact(ContactType.DRAIN)
        self.rng = np.random.default_rng(self.settings.seed)

        for name, cfg in channel_configs.items():
            if cfg.control_channel is not None:
                control = ControlChannel(cfg)
                control.set_parameter("slew_rate", instrument_config.slew_rate)
                self.add_channel(f"control_{name}", control)
            if cfg.measure_channel is not None:
                measure = MeasurementChannel(cfg)
                measure.get_parameter("current").getter = partial(
                    self._read_current, name
                )
                self.add_channel(f"measure_{name}", measure)

    def _single_contact(self, contact_type: ContactType) -> str:
        names = [
            name
            for name, cfg in self.channel_configs.items()
            if cfg.pad_type == PadType.CONTACT and cfg.electrode_type == contact_type
        ]
        if len(names) != 1:
            raise ValueError(
                f"simulator needs exactly one {contact_type.value} contact, "
                f"found {names}"
            )
        return names[0]

    def _voltage(self, pad: str) -> float:
        key = f"control_{pad}"
        return self.get_voltage(pad) if key in self.channels else 0.0

    def _channel_current(self) -> float:
        """Noiseless source-to-drain current (A), positive into the drain."""
        conductances = [
            gate_conductance(self._voltage(gate), params, self.polarity)
            for gate, params in self.turn_on.items()
        ]
        g_total = series_conductance(conductances, self.settings.series_resistance)
        bias = self._voltage(self.source) - self._voltage(self.drain)
        return channel_current(bias, g_total)

    def _read_current(self, pad: str) -> float:
        if pad == self.drain:
            ideal = self._channel_current()
        elif pad == self.source:
            ideal = -self._channel_current()
        else:
            ideal = 0.0  # no gate leakage modelled yet
        return noisy(ideal, self.settings.noise_std, self.rng)

    def set_voltage(self, channel_name: str, voltage: float) -> None:
        """Set the voltage on a pad. Out-of-bounds values raise ValueError."""
        super().set_voltage(f"control_{channel_name}", voltage)

    def get_voltage(self, channel_name: str) -> float:
        """Get the voltage on a pad."""
        return super().get_voltage(f"control_{channel_name}")

    def get_slew_rate(self, channel_name: str) -> float:
        """Get the slew rate on a pad (V/s)."""
        return super().get_slew_rate(f"control_{channel_name}")

    def set_slew_rate(self, channel_name: str, slew_rate: float) -> None:
        """Set the slew rate on a pad (V/s)."""
        super().set_slew_rate(f"control_{channel_name}", slew_rate)

    @overload
    def measure(self, channel_name: str) -> float: ...

    @overload
    def measure(self, channel_name: list[str]) -> list[float]: ...

    def measure(self, channel_name: str | list[str]) -> float | list[float]:
        """Measure current (A) on one pad or a list of pads."""
        if isinstance(channel_name, list):
            return [self.measure(name) for name in channel_name]
        return super().measure(f"measure_{channel_name}")

    @property
    def state(self) -> dict[str, Any]:
        """Current set voltages, for inspection and debugging."""
        return {
            name.removeprefix("control_"): channel.get_parameter_value("voltage")
            for name, channel in self.channels.items()
            if name.startswith("control_")
        }
