"""Physics simulator driver: a GENERAL instrument backed by trainer.physics models.

Loaded like any other Stanza driver (``driver: simulator`` in device YAML). One
instance is both the control and the measurement instrument, because computing a
current needs the gate voltages. Physics parameters come from the ``simulation``
block of the instrument entry, validated here at the boundary. This module
composes the pure functions in ``trainer.physics``; it holds no physics itself.

Minimal instrument entry (one implicit channel, pinch-off only)::

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
        series_resistance: 10000.0
        gates:
          P1: {v_threshold: 0.45, width: 0.05, g_max: 5.0e-5}

Devices with quantum dots add ``channels``, ``dots``, ``mutual`` and optionally
``leakage``, ``temperature``, ``lifetime_broadening`` and ``charge_noise``; see
``trainer/devices/dqd_with_sensor.yaml``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal, overload

import numpy as np
from numpy.typing import NDArray
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
from trainer.clock import VirtualClock
from trainer.physics.coulomb import (
    Dot,
    coulomb_resonance,
    dot_transmission,
    effective_induced_charge,
    induced_charge,
    joint_occupation,
    merged_dot,
    two_dot_transmission,
)
from trainer.physics.leakage import GROUND, LeakageLink, leakage_currents
from trainer.physics.noise import ou_step
from trainer.physics.pinchoff import (
    ELECTRON,
    HOLE,
    GateTurnOn,
    channel_current,
    noisy,
    series_conductance,
    turn_on,
)

MERGE_EXPONENT = 4
"""Inner-barrier turn-on is raised to this power to blend two dots into one."""


class TurnOnSettings(BaseModel):
    """Pinch-off parameters for the channel segment under one gate."""

    model_config = ConfigDict(extra="forbid")

    v_threshold: float
    width: PositiveFloat
    g_max: NonNegativeFloat


class DotSettings(BaseModel):
    """One quantum dot: charging energy, defining gates and lever arms."""

    model_config = ConfigDict(extra="forbid")

    charging_energy: float
    plunger: str
    barriers: list[str] = Field(default_factory=list)
    lever_arms: dict[str, NonNegativeFloat] = Field(default_factory=dict)
    charge_offset: float = 0.0

    @model_validator(mode="after")
    def positive_charging_energy(self) -> DotSettings:
        if self.charging_energy <= 0:
            raise ValueError(
                f"charging_energy must be positive, got {self.charging_energy}"
            )
        return self


class ChannelSettings(BaseModel):
    """A conduction path from a SOURCE to a DRAIN through gate segments and dots."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source: str
    drain: str
    segments: list[str] = Field(min_length=1)
    dots: list[str] = Field(default_factory=list)
    series_resistance: NonNegativeFloat | None = None


class MutualSettings(BaseModel):
    """Mutual charging energy between two dots (eV)."""

    model_config = ConfigDict(extra="forbid")

    dots: tuple[str, str]
    energy: NonNegativeFloat


class LeakageSettings(BaseModel):
    """A leakage path between two gates, or a gate and ``ground``."""

    model_config = ConfigDict(extra="forbid")

    gates: tuple[str, str]
    resistance: PositiveFloat
    onset: NonNegativeFloat = 0.0


class ChargeNoiseSettings(BaseModel):
    """Ornstein-Uhlenbeck noise on every dot's charge offset."""

    model_config = ConfigDict(extra="forbid")

    std: NonNegativeFloat
    tau: PositiveFloat


class SimulationSettings(BaseModel):
    """The ``simulation`` block of a simulator instrument entry."""

    model_config = ConfigDict(extra="forbid")

    seed: int = Field(ge=0)
    carrier: Literal["electron", "hole"]
    noise_std: NonNegativeFloat
    series_resistance: NonNegativeFloat
    gates: dict[str, TurnOnSettings]
    temperature: PositiveFloat = 4.0e-5
    lifetime_broadening: NonNegativeFloat = 0.0
    charge_noise: ChargeNoiseSettings | None = None
    channels: list[ChannelSettings] | None = None
    dots: dict[str, DotSettings] = Field(default_factory=dict)
    mutual: list[MutualSettings] = Field(default_factory=list)
    leakage: list[LeakageSettings] = Field(default_factory=list)

    @model_validator(mode="after")
    def matches_device(self, info: ValidationInfo) -> SimulationSettings:
        """Cross-check every name against the device the simulator is built for."""
        context = info.context or {}
        if "channel_gates" not in context:
            return self
        if self.channels is None:
            if self.dots:
                raise ValueError("simulation.dots requires simulation.channels")
            self._check_gate_coverage(context["channel_gates"])
        else:
            self._check_channels(context)
            self._check_dots(context["device_gates"])
        self._check_couplings(context["device_gates"])
        return self

    def _check_gate_coverage(self, expected: set[str]) -> None:
        missing = sorted(expected - self.gates.keys())
        unknown = sorted(self.gates.keys() - expected)
        if missing:
            raise ValueError(f"simulation.gates is missing turn-on for: {missing}")
        if unknown:
            raise ValueError(
                f"simulation.gates names gates not in the channel: {unknown}"
            )

    def _check_channels(self, context: dict[str, Any]) -> None:
        assert self.channels is not None
        device_gates: set[str] = context["device_gates"]
        used_contacts: set[str] = set()
        segments: set[str] = set()
        for ch in self.channels:
            unknown = [g for g in ch.segments if g not in device_gates]
            if unknown:
                raise ValueError(f"channel {ch.name}: unknown segment gates {unknown}")
            segments.update(ch.segments)
            if ch.source not in context["sources"]:
                raise ValueError(
                    f"channel {ch.name}: {ch.source} is not a SOURCE contact"
                )
            if ch.drain not in context["drains"]:
                raise ValueError(
                    f"channel {ch.name}: {ch.drain} is not a DRAIN contact"
                )
            for contact in (ch.source, ch.drain):
                if contact in used_contacts:
                    raise ValueError(f"contact {contact} is used by two channels")
                used_contacts.add(contact)
            if len(ch.dots) > 2:
                raise ValueError(
                    f"channel {ch.name}: at most two dots per channel, got {ch.dots}"
                )
        self._check_gate_coverage(segments)

    def _check_dots(self, device_gates: set[str]) -> None:
        assert self.channels is not None
        owner: dict[str, str] = {}
        for ch in self.channels:
            for d in ch.dots:
                if d in owner:
                    raise ValueError(f"dot {d} is in channels {owner[d]} and {ch.name}")
                if d not in self.dots:
                    raise ValueError(f"channel {ch.name}: unknown dot {d}")
                owner[d] = ch.name
                dot = self.dots[d]
                for g in [dot.plunger, *dot.barriers]:
                    if g not in ch.segments:
                        raise ValueError(
                            f"dot {d}: gate {g} is not a segment of channel {ch.name}"
                        )
            if len(ch.dots) == 2:
                a, b = (self.dots[d] for d in ch.dots)
                if len(set(a.barriers) & set(b.barriers)) != 1:
                    raise ValueError(
                        f"channel {ch.name}: dots {ch.dots} must share exactly one "
                        "barrier (the inner barrier)"
                    )
        orphans = sorted(set(self.dots) - owner.keys())
        if orphans:
            raise ValueError(f"dots not placed in any channel: {orphans}")
        for d, dot in self.dots.items():
            unknown = sorted(set(dot.lever_arms) - device_gates)
            if unknown:
                raise ValueError(f"dot {d}: lever arms to unknown gates {unknown}")

    def _check_couplings(self, device_gates: set[str]) -> None:
        for m in self.mutual:
            for d in m.dots:
                if d not in self.dots:
                    raise ValueError(f"mutual: unknown dot {d}")
            if m.dots[0] == m.dots[1]:
                raise ValueError(f"mutual: dot {m.dots[0]} cannot couple to itself")
        for link in self.leakage:
            for g in link.gates:
                if g != GROUND and g not in device_gates:
                    raise ValueError(f"leakage: unknown gate {g}")
            if link.gates[0] == link.gates[1]:
                raise ValueError(f"leakage: gate {link.gates[0]} links to itself")


class _SimulatorExtras(BaseModel):
    simulation: SimulationSettings


@dataclass(frozen=True)
class SimulatedChannel:
    """A resolved conduction channel."""

    name: str
    source: str
    drain: str
    segments: tuple[str, ...]
    dots: tuple[str, ...]
    series_resistance: float
    inner_barrier: str | None = None
    merged_charging_energy: float | None = None


class Simulator(GeneralInstrument):
    """Simulated quantum-dot device exposed as a Stanza GENERAL instrument."""

    def __init__(
        self,
        instrument_config: GeneralInstrumentConfig,
        channel_configs: dict[str, ChannelConfig],
    ) -> None:
        super().__init__(instrument_config)
        self.channel_configs = channel_configs

        def of_type(pad: PadType, kind: GateType | ContactType) -> set[str]:
            return {
                n
                for n, c in channel_configs.items()
                if c.pad_type == pad and c.electrode_type == kind
            }

        device_gates = {
            n for n, c in channel_configs.items() if c.pad_type == PadType.GATE
        }
        context = {
            "device_gates": device_gates,
            "channel_gates": device_gates - of_type(PadType.GATE, GateType.SCREEN),
            "sources": of_type(PadType.CONTACT, ContactType.SOURCE),
            "drains": of_type(PadType.CONTACT, ContactType.DRAIN),
        }
        extras = _SimulatorExtras.model_validate(
            instrument_config.model_extra or {}, context=context
        )
        self.settings = extras.simulation
        self.polarity = ELECTRON if self.settings.carrier == "electron" else HOLE
        self.turn_on = {
            name: GateTurnOn(s.v_threshold, s.width, s.g_max)
            for name, s in self.settings.gates.items()
        }
        self.dots = {
            name: Dot(d.charging_energy, dict(d.lever_arms), d.charge_offset)
            for name, d in self.settings.dots.items()
        }
        self._mutual = {
            frozenset(m.dots): m.energy for m in self.settings.mutual if m.energy > 0
        }
        self._links = [
            LeakageLink(lk.gates[0], lk.gates[1], lk.resistance, lk.onset)
            for lk in self.settings.leakage
        ]
        self.conduction_channels = self._resolve_channels()
        self._dot_channel = {
            d: c.name for c in self.conduction_channels for d in c.dots
        }
        self._dot_order = sorted(self.dots)
        self._interaction, self._sensing = self._coupling_matrices()

        self.rng = np.random.default_rng(self.settings.seed)
        self.clock = VirtualClock()
        self.measurement_duration = float(instrument_config.measurement_duration)
        self._charge_noise = dict.fromkeys(sorted(self.dots), 0.0)
        self._noise_time = 0.0
        self._voltages: dict[str, float] = {}
        self.reading_count = 0

        for name, cfg in channel_configs.items():
            if cfg.control_channel is not None:
                control = ControlChannel(cfg)
                control.set_parameter("slew_rate", instrument_config.slew_rate)
                self.add_channel(f"control_{name}", control)
                self._voltages[name] = 0.0
            if cfg.measure_channel is not None:
                measure = MeasurementChannel(cfg)
                measure.get_parameter("current").getter = partial(
                    self._read_current, name
                )
                self.add_channel(f"measure_{name}", measure)

    # --- setup -------------------------------------------------------------

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

    def _resolve_channels(self) -> list[SimulatedChannel]:
        default_r = self.settings.series_resistance
        if self.settings.channels is None:
            return [
                SimulatedChannel(
                    name="channel",
                    source=self._single_contact(ContactType.SOURCE),
                    drain=self._single_contact(ContactType.DRAIN),
                    segments=tuple(self.turn_on),
                    dots=(),
                    series_resistance=default_r,
                )
            ]
        resolved = []
        for ch in self.settings.channels:
            inner, merged_ec = None, None
            if len(ch.dots) == 2:
                a, b = ch.dots
                shared = set(self.settings.dots[a].barriers) & set(
                    self.settings.dots[b].barriers
                )
                inner = shared.pop()
                merged_ec = merged_dot(
                    self.dots[a], self.dots[b], self._mutual_energy(a, b)
                ).charging_energy
            resolved.append(
                SimulatedChannel(
                    name=ch.name,
                    source=ch.source,
                    drain=ch.drain,
                    segments=tuple(ch.segments),
                    dots=tuple(ch.dots),
                    series_resistance=(
                        default_r
                        if ch.series_resistance is None
                        else ch.series_resistance
                    ),
                    inner_barrier=inner,
                    merged_charging_energy=merged_ec,
                )
            )
        return resolved

    def _mutual_energy(self, a: str, b: str) -> float:
        return self._mutual.get(frozenset((a, b)), 0.0)

    def _coupling_matrices(self) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """U: charging energies and same-channel mutual terms. W: sensed terms."""
        k = len(self._dot_order)
        u, w = np.zeros((k, k)), np.zeros((k, k))
        for i, a in enumerate(self._dot_order):
            u[i, i] = self.dots[a].charging_energy
            for j, b in enumerate(self._dot_order):
                if i == j:
                    continue
                em = self._mutual_energy(a, b)
                same = self._dot_channel[a] == self._dot_channel[b]
                (u if same else w)[i, j] = em
        return u, w

    # --- physics composition ---------------------------------------------

    def _advance_charge_noise(self) -> None:
        noise = self.settings.charge_noise
        now = self.clock.now()
        dt = now - self._noise_time
        if noise is None or dt <= 0:
            self._noise_time = now
            return
        for d in self._charge_noise:
            self._charge_noise[d] = ou_step(
                self._charge_noise[d], dt, noise.tau, noise.std, self.rng
            )
        self._noise_time = now

    def _bare_induced_charges(self) -> dict[str, float]:
        return {
            d: induced_charge(dot, self._voltages, self.polarity)
            + self._charge_noise[d]
            for d, dot in self.dots.items()
        }

    def _induced_charges(
        self,
    ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        """Induced charges shifted by sensed charges, bare induced charges, and
        exact thermal occupations of every dot."""
        bare = self._bare_induced_charges()
        if not bare:
            return {}, {}, {}
        n0 = np.array([bare[d] for d in self._dot_order])
        occ = joint_occupation(
            n0, self._interaction, self._sensing, self.settings.temperature
        )
        ec = np.diag(self._interaction)
        shifted = n0 - (self._sensing @ occ) / ec
        names = self._dot_order
        return (
            {d: float(x) for d, x in zip(names, shifted, strict=True)},
            bare,
            {d: float(x) for d, x in zip(names, occ, strict=True)},
        )

    def _turn_on(self, gate: str) -> float:
        return turn_on(self._voltages.get(gate, 0.0), self.turn_on[gate], self.polarity)

    def _openness(self, gates: list[str], transmissions: dict[str, float]) -> float:
        return math.prod(transmissions[g] for g in gates)

    def _resonance(self, n0: float, charging_energy: float, openness: float) -> float:
        kT = self.settings.temperature + self.settings.lifetime_broadening * openness
        return coulomb_resonance(n0, charging_energy, kT)

    def _dot_factor(
        self,
        channel: SimulatedChannel,
        t: dict[str, float],
        n0: dict[str, float],
        bare: dict[str, float],
        occupation: dict[str, float],
    ) -> float:
        if not channel.dots:
            return 1.0
        defs = self.settings.dots
        if len(channel.dots) == 1:
            (d,) = channel.dots
            o = self._openness([defs[d].plunger, *defs[d].barriers], t)
            return dot_transmission(
                self._resonance(n0[d], self.dots[d].charging_energy, o), o
            )
        a, b = channel.dots
        em = self._mutual_energy(a, b)
        o_a = self._openness([defs[a].plunger, *defs[a].barriers], t)
        o_b = self._openness([defs[b].plunger, *defs[b].barriers], t)
        ec_a, ec_b = self.dots[a].charging_energy, self.dots[b].charging_energy
        n0_a = effective_induced_charge(
            n0[a], ec_a, [(em, occupation[b] - max(bare[b], 0.0))]
        )
        n0_b = effective_induced_charge(
            n0[b], ec_b, [(em, occupation[a] - max(bare[a], 0.0))]
        )
        assert channel.inner_barrier is not None
        assert channel.merged_charging_energy is not None
        outer = sorted({*defs[a].barriers, *defs[b].barriers} - {channel.inner_barrier})
        o_m = self._openness([defs[a].plunger, defs[b].plunger, *outer], t)
        merged = dot_transmission(
            self._resonance(n0[a] + n0[b], channel.merged_charging_energy, o_m), o_m
        )
        return two_dot_transmission(
            self._resonance(n0_a, ec_a, o_a),
            self._resonance(n0_b, ec_b, o_b),
            o_a,
            o_b,
            t[channel.inner_barrier] ** MERGE_EXPONENT,
            merged,
        )

    def _channel_current(
        self,
        channel: SimulatedChannel,
        n0: dict[str, float],
        bare: dict[str, float],
        occupation: dict[str, float],
    ) -> float:
        """Noiseless source-to-drain current (A), positive into the drain."""
        t = {g: self._turn_on(g) for g in channel.segments}
        g_total = series_conductance(
            [self.turn_on[g].g_max * t[g] for g in channel.segments],
            channel.series_resistance,
        )
        if g_total == 0.0:
            return 0.0
        bias = self._voltages.get(channel.source, 0.0) - self._voltages.get(
            channel.drain, 0.0
        )
        factor = self._dot_factor(channel, t, n0, bare, occupation)
        return channel_current(bias, g_total * factor)

    def _ideal_current(self, pad: str) -> float:
        for ch in self.conduction_channels:
            if pad in (ch.source, ch.drain):
                n0, bare, occupation = self._induced_charges()
                i = self._channel_current(ch, n0, bare, occupation)
                return i if pad == ch.drain else -i
        if not self._links:
            return 0.0
        return leakage_currents(self._voltages, self._links).get(pad, 0.0)

    def _read_current(self, pad: str) -> float:
        self.reading_count += 1
        self._advance_charge_noise()
        value = noisy(self._ideal_current(pad), self.settings.noise_std, self.rng)
        self.clock.advance(self.measurement_duration)
        return value

    # --- inspection (simulator ground truth; not visible to routines) ----------

    def ideal_current(self, pad: str, overrides: dict[str, float]) -> float:
        """Noiseless current on ``pad`` with some voltages overridden.

        Read-only: no clock advance, no randomness, not counted as a reading, and
        charge noise is excluded. For judging levels, never for routines.
        """
        unknown = sorted(set(overrides) - set(self._voltages))
        if unknown:
            raise KeyError(f"unknown or uncontrollable pads: {unknown}")
        saved_v, saved_noise = self._voltages, self._charge_noise
        self._voltages = {**saved_v, **overrides}
        self._charge_noise = dict.fromkeys(saved_noise, 0.0)
        try:
            return self._ideal_current(pad)
        finally:
            self._voltages, self._charge_noise = saved_v, saved_noise

    def dot_openness(self, dot: str) -> float:
        """Product of the turn-ons of the dot's plunger and barriers (1 = open wire)."""
        settings = self.settings.dots[dot]
        gates = [settings.plunger, *settings.barriers]
        return math.prod(self._turn_on(g) for g in gates)

    def occupations(self) -> dict[str, float]:
        """Thermal average charge on each dot at the present voltages."""
        return self._induced_charges()[2]

    def transition_voltage(self, dot: str, gate: str, n: int) -> float:
        """Voltage on ``gate`` (others fixed) where ``dot`` goes from n to n+1 charges.

        Includes charges sensed from other channels, but not interactions with a
        dot in the same channel.
        """
        model = self.dots[dot]
        alpha = model.lever_arms.get(gate, 0.0)
        if alpha == 0.0:
            raise ValueError(f"dot {dot} has no lever arm to gate {gate}")
        n0, _, _ = self._induced_charges()
        own = self.polarity * alpha * self._voltages.get(gate, 0.0)
        rest = n0[dot] - own / model.charging_energy
        return (n + 0.5 - rest) * model.charging_energy / (self.polarity * alpha)

    # --- instrument API ----------------------------------------------------------

    def set_voltage(self, channel_name: str, voltage: float) -> None:
        """Set the voltage on a pad. Out-of-bounds values raise ValueError."""
        super().set_voltage(f"control_{channel_name}", voltage)
        self._voltages[channel_name] = float(voltage)

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
        return dict(self._voltages)
