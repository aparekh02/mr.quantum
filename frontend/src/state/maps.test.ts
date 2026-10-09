import { describe, expect, it } from "vitest";
import type { TrainerEvent } from "../api/types";
import { MapAccumulator } from "./maps";

let seq = 0;
const ev = (kind: TrainerEvent["kind"], name: string, data: unknown): TrainerEvent => {
  seq += 1;
  return { seq, time: 0, kind, routine: "charge_stability_diagram", name, data };
};

function feedGrid(acc: MapAccumulator, nx: number, ny: number, complete: boolean) {
  const xs: number[][] = [];
  const ys: number[] = [];
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const x = [j * 0.1, i * 0.01]; // [outer (y gate), inner (x gate)]
      const y = [i + 100 * j];
      acc.apply(ev("sweep_point", "PA2 and PA1 sweep", { x, y }));
      xs.push(x);
      ys.push(y[0]!);
    }
  }
  if (complete) {
    acc.apply(
      ev("sweep", "PA2 and PA1 sweep", { x_label: ["PA2", "PA1"], y_label: "Current", x_data: xs, y_data: ys }),
    );
  }
}

describe("MapAccumulator", () => {
  it("builds a grid with the inner gate horizontal and the outer gate vertical", () => {
    const acc = new MapAccumulator();
    feedGrid(acc, 4, 3, true);
    const map = acc.latest();
    expect(map).not.toBeNull();
    expect(map?.xGate).toBe("PA1");
    expect(map?.yGate).toBe("PA2");
    expect(map?.xs).toEqual([0, 0.01, 0.02, 0.03]);
    expect(map?.ys).toEqual([0, 0.1, 0.2]);
    expect(map?.complete).toBe(true);
    // value(i, j) = i + 100 j  at row j, column i
    expect(map?.value(3, 2)).toBe(203);
    expect(map?.value(0, 1)).toBe(100);
  });

  it("shows partial maps while points stream in", () => {
    const acc = new MapAccumulator();
    feedGrid(acc, 5, 2, false);
    const map = acc.latest();
    expect(map?.complete).toBe(false);
    expect(map?.xs).toHaveLength(5);
    expect(map?.ys).toHaveLength(2);
    expect(map?.xGate).toBeNull(); // labels only arrive with the finished sweep
  });

  it("missing cells are NaN", () => {
    const acc = new MapAccumulator();
    acc.apply(ev("sweep_point", "s", { x: [0, 0], y: [1] }));
    acc.apply(ev("sweep_point", "s", { x: [0, 1], y: [2] }));
    acc.apply(ev("sweep_point", "s", { x: [1, 0], y: [3] }));
    expect(Number.isNaN(acc.latest()?.value(1, 1))).toBe(true);
  });

  it("ignores 1D sweeps and other events, and bumps a version on change", () => {
    const acc = new MapAccumulator();
    const v0 = acc.version;
    acc.apply(ev("sweep_point", "1d", { x: [0.1], y: [1] }));
    acc.apply(ev("analysis", "a", {}));
    expect(acc.latest()).toBeNull();
    expect(acc.version).toBe(v0);
    acc.apply(ev("sweep_point", "2d", { x: [0, 0], y: [1] }));
    expect(acc.version).toBe(v0 + 1);
  });

  it("a new 2D sweep replaces the previous one", () => {
    const acc = new MapAccumulator();
    feedGrid(acc, 2, 2, true);
    acc.apply(ev("sweep_point", "other", { x: [5, 5], y: [9] }));
    expect(acc.latest()?.title).toContain("other");
  });

  it("handles 10,000 streamed points quickly", () => {
    const acc = new MapAccumulator();
    const t0 = performance.now();
    feedGrid(acc, 100, 100, true);
    const map = acc.latest();
    const elapsed = performance.now() - t0;
    expect(map?.xs).toHaveLength(100);
    expect(elapsed).toBeLessThan(500);
  });
});

describe("MapAccumulator and charge-stability measurements", () => {
  function csdEvents(n: number) {
    const gates = ["RA1", "BA0", "PA1", "BA1", "PA2", "BA2", "RA2"];
    const voltages: number[][][] = [];
    const currents: number[][] = [];
    for (let j = 0; j < n; j++) {
      const row: number[][] = [];
      const crow: number[] = [];
      for (let i = 0; i < n; i++) {
        row.push([-1.7, -1.1, -0.66 + 0.002 * i, -0.88, -0.64 + 0.002 * j, -1.1, -1.7]);
        crow.push(i + 10 * j);
      }
      voltages.push(row);
      currents.push(crow);
    }
    return [
      ev("run_started", "run_dqd_search", { run_id: "r", parameters: { gates } }),
      ev("measurement", "dqd_search_high_res_csd", { voltages, currents, grid_idx: 3 }),
    ];
  }

  it("turns a logged CSD measurement into a map with the plunger gates as axes", () => {
    const acc = new MapAccumulator();
    for (const e of csdEvents(4)) acc.apply({ ...e, routine: "run_dqd_search" });
    const map = acc.latest();
    expect(map?.xGate).toBe("PA1");
    expect(map?.yGate).toBe("PA2");
    expect(map?.xs).toEqual([-0.66, -0.658, -0.656, -0.654].map((v) => expect.closeTo(v, 12)));
    expect(map?.value(3, 2)).toBe(23);
    expect(map?.complete).toBe(true);
    expect(map?.title).toBe("run_dqd_search: dqd_search_high_res_csd");
  });

  it("without the run's gate list the axes stay unlabelled", () => {
    const acc = new MapAccumulator();
    const [, measurement] = csdEvents(3);
    if (!measurement) throw new Error("no event");
    acc.apply({ ...measurement, routine: "run_dqd_search" });
    expect(acc.latest()?.xGate).toBeNull();
    expect(acc.latest()?.xs).toHaveLength(3);
  });

  it("ignores measurements that are not 2D maps", () => {
    const acc = new MapAccumulator();
    acc.apply(ev("measurement", "dqd_search_current_trace", { voltages: [[0, 1]], currents: [1, 2] }));
    expect(acc.latest()).toBeNull();
  });
});
