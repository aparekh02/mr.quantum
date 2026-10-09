import { describe, expect, it } from "vitest";
import { clampToBounds, dataToPixel, fullView, pan, pixelToData, zoomAt } from "./viewport";

const size = { width: 400, height: 200 };
const full = fullView([-1, 1], [0, 2]);

describe("viewport", () => {
  it("maps the edges exactly", () => {
    expect(pixelToData(0, 0, full, size)).toEqual({ x: -1, y: 2 }); // top-left = max y
    expect(pixelToData(400, 200, full, size)).toEqual({ x: 1, y: 0 });
    expect(pixelToData(200, 100, full, size)).toEqual({ x: 0, y: 1 });
  });

  it("round-trips data -> pixel -> data", () => {
    const p = dataToPixel(0.37, 1.21, full, size);
    const d = pixelToData(p.px, p.py, full, size);
    expect(d.x).toBeCloseTo(0.37, 12);
    expect(d.y).toBeCloseTo(1.21, 12);
  });

  it("zooming at a point keeps that point under the cursor", () => {
    const cursor = { px: 100, py: 50 };
    const before = pixelToData(cursor.px, cursor.py, full, size);
    const zoomed = zoomAt(full, cursor.px, cursor.py, 2, size);
    const after = pixelToData(cursor.px, cursor.py, zoomed, size);
    expect(after.x).toBeCloseTo(before.x, 12);
    expect(after.y).toBeCloseTo(before.y, 12);
    expect(zoomed.x1 - zoomed.x0).toBeCloseTo(1, 12); // 2x zoom halves the span
  });

  it("maps edges correctly after zoom", () => {
    const zoomed = zoomAt(full, 200, 100, 4, size);
    expect(pixelToData(0, 200, zoomed, size).x).toBeCloseTo(-0.25, 12);
    expect(pixelToData(400, 0, zoomed, size).y).toBeCloseTo(1.25, 12);
  });

  it("panning moves the view by the dragged distance", () => {
    const moved = pan(full, 100, 0, size); // drag right by a quarter width
    expect(moved.x0).toBeCloseTo(-1.5, 12);
    expect(moved.x1).toBeCloseTo(0.5, 12);
    const up = pan(full, 0, 50, size); // drag down: content moves down, view moves up
    expect(up.y0).toBeCloseTo(0.5, 12);
  });

  it("clamps to the data extent and never zooms out past it", () => {
    const out = zoomAt(full, 200, 100, 0.25, size);
    expect(clampToBounds(out, full)).toEqual(full);
    const panned = clampToBounds(pan(full, 1000, 0, size), full);
    expect(panned).toEqual(full);
    const z = zoomAt(full, 0, 0, 2, size);
    const shifted = clampToBounds(pan(z, 400, 0, size), full);
    expect(shifted.x0).toBeCloseTo(-1, 12);
    expect(shifted.x1 - shifted.x0).toBeCloseTo(1, 12);
  });

  it("supports descending data axes", () => {
    const desc = fullView([1, -1], [0, 2]);
    expect(pixelToData(0, 200, desc, size).x).toBe(-1);
  });
});
