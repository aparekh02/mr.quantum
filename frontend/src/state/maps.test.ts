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
