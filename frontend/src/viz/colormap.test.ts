import { describe, expect, it } from "vitest";
import { colorAt, limits, VIRIDIS_STOPS } from "./colormap";

describe("colormap", () => {
  it("maps the limits to the end stops and clamps outside", () => {
    expect(colorAt(0, 0, 1)).toEqual(VIRIDIS_STOPS[0]);
    expect(colorAt(1, 0, 1)).toEqual(VIRIDIS_STOPS.at(-1));
    expect(colorAt(-5, 0, 1)).toEqual(VIRIDIS_STOPS[0]);
    expect(colorAt(9, 0, 1)).toEqual(VIRIDIS_STOPS.at(-1));
  });

  it("golden values: midpoint and quarter points", () => {
    // Stops are evenly spaced; 0.5 lands exactly on the middle stop of 9.
    expect(colorAt(0.5, 0, 1)).toEqual(VIRIDIS_STOPS[4]);
    // 0.0625 is halfway between stop 0 and stop 1: linear interpolation.
    const [a, b] = [VIRIDIS_STOPS[0]!, VIRIDIS_STOPS[1]!];
    expect(colorAt(0.0625, 0, 1)).toEqual([
      Math.round((a[0] + b[0]) / 2),
      Math.round((a[1] + b[1]) / 2),
      Math.round((a[2] + b[2]) / 2),
    ]);
  });

  it("is scale invariant: real currents behave like normalised ones", () => {
    expect(colorAt(3e-10, 1e-10, 5e-10)).toEqual(colorAt(0.5, 0, 1));
  });

  it("a flat map is drawn in the middle colour, not NaN", () => {
    expect(colorAt(2, 2, 2)).toEqual(VIRIDIS_STOPS[4]);
  });

  it("non-finite values get the 'missing' colour", () => {
    expect(colorAt(Number.NaN, 0, 1)).toEqual([0, 0, 0]);
  });

  it("limits use robust percentiles so one outlier cannot wash out the map", () => {
    const values = Float64Array.from({ length: 1000 }, (_, i) => i);
    values[500] = 1e9; // a glitch
    const [lo, hi] = limits(values, 0.01);
    expect(lo).toBe(10);
    expect(hi).toBe(990);
  });

  it("limits ignore NaN and handle empty or tiny inputs", () => {
    expect(limits(Float64Array.from([Number.NaN, 2, 4]), 0)).toEqual([2, 4]);
    expect(limits(new Float64Array(0), 0.01)).toEqual([0, 1]);
    expect(limits(Float64Array.from([7]), 0.01)).toEqual([7, 7]);
  });
});
