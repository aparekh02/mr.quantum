import { useEffect, useRef, useState } from "react";
import type { PadInfo, Voltages } from "../api/types";
import { formatVolts } from "../state/summary";

interface Props {
  pads: PadInfo[];
  voltages: Voltages;
  onSet: (voltages: Voltages) => Promise<Voltages>;
  disabled?: boolean;
}

// One slider per controllable pad. Dragging shows the new value at once; requests
// go out one at a time, and while one is in flight only the newest value per pad
// is kept. A rejected request reverts to the last value the server confirmed.
export function GateSliders({ pads, voltages, onSet, disabled = false }: Props) {
  const [display, setDisplay] = useState<Voltages>(voltages);
  const [error, setError] = useState<string | null>(null);
  const confirmed = useRef<Voltages>(voltages);
  const inFlight = useRef(false);
  const queued = useRef<Voltages>({});

  useEffect(() => {
    confirmed.current = voltages;
    if (!inFlight.current) setDisplay(voltages);
  }, [voltages]);

  async function flush(): Promise<void> {
    if (inFlight.current || Object.keys(queued.current).length === 0) return;
    const batch = queued.current;
    queued.current = {};
    inFlight.current = true;
    try {
      const server = await onSet(batch);
      confirmed.current = server;
      setError(null);
      setDisplay((d) => ({ ...server, ...pick(d, Object.keys(queued.current)) }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setDisplay((d) => ({ ...d, ...pick(confirmed.current, Object.keys(batch)) }));
    } finally {
      inFlight.current = false;
    }
    await flush();
  }

  function change(pad: string, value: number): void {
    setDisplay((d) => ({ ...d, [pad]: value }));
    queued.current = { ...queued.current, [pad]: value };
    void flush();
  }

  const controllable = pads.filter((p) => p.controllable);
  return (
    <section className="sliders" aria-label="Gate voltages">
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {controllable.map((pad) => {
        const value = display[pad.name] ?? 0;
        return (
          <label key={pad.name} className="slider">
            <span className="pad-name">{pad.name}</span>
            <input
              type="range"
              aria-label={pad.name}
              min={pad.v_lower_bound ?? -1}
              max={pad.v_upper_bound ?? 1}
              step={0.0001}
              value={value}
              disabled={disabled}
              onChange={(e) => change(pad.name, Number(e.target.value))}
            />
            <output data-testid={`value-${pad.name}`}>{formatVolts(value)}</output>
          </label>
        );
      })}
    </section>
  );
}

function pick(source: Voltages, keys: string[]): Voltages {
  return Object.fromEntries(keys.filter((k) => k in source).map((k) => [k, source[k] as number]));
}
