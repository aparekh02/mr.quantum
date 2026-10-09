import { type FormEvent, useState } from "react";
import type { PadInfo, Voltages } from "../api/types";

interface Props {
  pads: PadInfo[];
  voltages: Voltages;
  onRun: (routine: string, parameters: Record<string, unknown>) => Promise<void>;
  running: boolean;
}

const HALF_WINDOW = 0.04;
const round = (v: number) => Math.round(v * 1e6) / 1e6;

function defaultWindow(pad: PadInfo | undefined, centre: number): [number, number] {
  const lo = pad?.v_lower_bound ?? Number.NEGATIVE_INFINITY;
  const hi = pad?.v_upper_bound ?? Number.POSITIVE_INFINITY;
  return [round(Math.max(lo, centre - HALF_WINDOW)), round(Math.min(hi, centre + HALF_WINDOW))];
}

export function CsdPanel({ pads, voltages, onRun, running }: Props) {
  const gates = pads.filter((p) => p.pad_type === "GATE" && p.controllable);
  const plungers = gates.filter((p) => p.electrode_type === "PLUNGER");
  const [gx, gy] = [plungers[0] ?? gates[0], plungers[1] ?? gates[1]];
  const [gateX, setGateX] = useState(gx?.name ?? "");
  const [gateY, setGateY] = useState(gy?.name ?? "");
  const [xRange, setXRange] = useState<[number, number] | null>(null);
  const [yRange, setYRange] = useState<[number, number] | null>(null);
  const [points, setPoints] = useState(48);
  const [error, setError] = useState<string | null>(null);

  const pad = (name: string) => gates.find((g) => g.name === name);
  const shownX = xRange ?? defaultWindow(pad(gateX), voltages[gateX] ?? 0);
  const shownY = yRange ?? defaultWindow(pad(gateY), voltages[gateY] ?? 0);

  function drainFor(gate: string): string | undefined {
    const group = pad(gate)?.group;
    const drains = pads.filter((p) => p.measurable && p.electrode_type === "DRAIN");
    return (drains.find((d) => d.group === group) ?? drains[0])?.name;
  }

  async function submit(e: FormEvent): Promise<void> {
    e.preventDefault();
    if (gateX === gateY) {
      setError("Choose two different gates");
      return;
    }
    setError(null);
    try {
      await onRun("charge_stability_diagram", {
        gate_x: gateX,
        gate_y: gateY,
        x_range: shownX,
        y_range: shownY,
        points,
        measure_electrode: drainFor(gateX),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const gateSelect = (label: string, value: string, set: (v: string) => void, reset: () => void) => (
    <label>
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={(e) => {
          set(e.target.value);
          reset();
        }}
      >
        {gates.map((g) => (
          <option key={g.name} value={g.name}>
            {g.name}
          </option>
        ))}
      </select>
    </label>
  );

  const num = (label: string, value: number, set: (v: number) => void) => (
    <label>
      {label}
      <input
        aria-label={label}
        type="number"
        step="any"
        value={value}
        onChange={(e) => set(Number(e.target.value))}
      />
    </label>
  );

  return (
    <form className="csd-panel" onSubmit={(e) => void submit(e)}>
      {gateSelect("X gate", gateX, setGateX, () => setXRange(null))}
      {num("X from (V)", shownX[0], (v) => setXRange([v, shownX[1]]))}
      {num("X to (V)", shownX[1], (v) => setXRange([shownX[0], v]))}
      {gateSelect("Y gate", gateY, setGateY, () => setYRange(null))}
      {num("Y from (V)", shownY[0], (v) => setYRange([v, shownY[1]]))}
      {num("Y to (V)", shownY[1], (v) => setYRange([shownY[0], v]))}
      {num("Points per axis", points, setPoints)}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button type="submit" disabled={running}>
        Measure map
      </button>
    </form>
  );
}
