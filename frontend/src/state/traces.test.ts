import { describe, expect, it } from "vitest";
import type { TrainerEvent } from "../api/types";
import { applyEvent, applyEvents, emptyTraces } from "./traces";

let seq = 0;
function ev(kind: TrainerEvent["kind"], name: string, data: unknown, routine = "r"): TrainerEvent {
  seq += 1;
  return { seq, time: seq, kind, routine, name, data };
}

describe("trace reducer", () => {
  it("builds a live trace from sweep points", () => {
    let s = emptyTraces;
    s = applyEvent(s, ev("sweep_point", "P1 sweep", { x: [0.1], y: [1e-9] }));
    s = applyEvent(s, ev("sweep_point", "P1 sweep", { x: [0.2], y: [2e-9] }));
    expect(s.latest?.points).toEqual([
      { x: 0.1, y: 1e-9 },
      { x: 0.2, y: 2e-9 },
    ]);
    expect(s.latest?.complete).toBe(false);
    expect(s.latest?.title).toBe("r: P1 sweep");
  });

  it("a new sweep name starts a new trace", () => {
    let s = emptyTraces;
    s = applyEvent(s, ev("sweep_point", "a", { x: [0], y: [1] }));
    s = applyEvent(s, ev("sweep_point", "b", { x: [5], y: [6] }));
    expect(s.latest?.title).toBe("r: b");
    expect(s.latest?.points).toEqual([{ x: 5, y: 6 }]);
  });

  it("a completed 1D sweep replaces the live trace with the full data", () => {
    let s = emptyTraces;
    s = applyEvent(s, ev("sweep_point", "a", { x: [0], y: [1] }));
    s = applyEvent(
      s,
      ev("sweep", "a", { x_label: "Voltage", y_label: "Current", x_data: [[0], [1]], y_data: [1, 2] }),
    );
    expect(s.latest).toMatchObject({
      complete: true,
      xLabel: "Voltage",
      yLabel: "Current",
      points: [
        { x: 0, y: 1 },
        { x: 1, y: 2 },
      ],
    });
    expect(s.completed).toHaveLength(1);
  });

  it("an n-gate sweep is plotted against the gate that moves the most", () => {
    const s = applyEvent(
      emptyTraces,
      ev("sweep", "n gates sweep", {
        x_label: "Voltage",
        y_label: "Current",
        x_data: [
          [0.5, 0.0],
          [0.5, -0.1],
          [0.5, -0.2],
        ],
        y_data: [1, 2, 3],
      }),
    );
    expect(s.latest?.points.map((p) => p.x)).toEqual([0.0, -0.1, -0.2]);
  });

  it("accepts flat x data", () => {
    const s = applyEvent(
      emptyTraces,
      ev("sweep", "s", { x_label: "V", y_label: "I", x_data: [1, 2], y_data: [3, 4] }),
    );
    expect(s.latest?.points).toEqual([
      { x: 1, y: 3 },
      { x: 2, y: 4 },
    ]);
  });

  it("drops non-finite points and ignores unrelated events", () => {
    let s = emptyTraces;
    s = applyEvent(s, ev("sweep_point", "a", { x: [0], y: [null] }));
    s = applyEvent(s, ev("measurement", "m", { v: 1 }));
    s = applyEvent(s, ev("run_started", "r", {}));
    expect(s.latest?.points ?? []).toEqual([]);
  });

  it("keeps only the most recent completed traces", () => {
    let s = emptyTraces;
    for (let i = 0; i < 30; i++) {
      s = applyEvent(s, ev("sweep", `s${i}`, { x_label: "V", y_label: "I", x_data: [0], y_data: [i] }));
    }
    expect(s.completed).toHaveLength(20);
    expect(s.completed.at(-1)?.title).toBe("r: s29");
  });
});

describe("trace reducer and 2D data", () => {
  it("leaves 2D sweep points and 2D sweeps to the map view", () => {
    let s = emptyTraces;
    s = applyEvent(s, ev("sweep_point", "PA2 and PA1 sweep", { x: [0.1, 0.2], y: [1] }));
    s = applyEvent(
      s,
      ev("sweep", "PA2 and PA1 sweep", { x_label: ["PA2", "PA1"], y_label: "I", x_data: [[0, 0]], y_data: [1] }),
    );
    expect(s).toBe(emptyTraces);
  });
});

describe("applyEvents (batched)", () => {
  it("matches applying events one by one", () => {
    const events = Array.from({ length: 50 }, (_, i) => ev("sweep_point", "live", { x: [i], y: [i * 2] }));
    const one = events.reduce(applyEvent, emptyTraces);
    expect(applyEvents(emptyTraces, events)).toEqual(one);
  });

  it("appends 10,000 live points in linear time", () => {
    const events = Array.from({ length: 10_000 }, (_, i) => ev("sweep_point", "big", { x: [i], y: [i] }));
    const t0 = performance.now();
    const s = applyEvents(emptyTraces, events);
    expect(performance.now() - t0).toBeLessThan(200);
    expect(s.latest?.points).toHaveLength(10_000);
  });
});
