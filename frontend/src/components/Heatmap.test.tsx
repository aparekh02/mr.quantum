import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MapData } from "../state/maps";
import { Heatmap, renderRGBA } from "./Heatmap";

function makeMap(nx: number, ny: number): MapData {
  const xs = Array.from({ length: nx }, (_, i) => -0.66 + (0.08 * i) / (nx - 1));
  const ys = Array.from({ length: ny }, (_, j) => -0.66 + (0.08 * j) / (ny - 1));
  const values = Float64Array.from({ length: nx * ny }, (_, k) => k);
  return {
    key: "k",
    title: "charge_stability_diagram: PA2 and PA1 sweep",
    xGate: "PA1",
    yGate: "PA2",
    xs,
    ys,
    values,
    complete: true,
    value: (i, j) => values[j * nx + i] ?? Number.NaN,
  };
}

// jsdom has no canvas: give the component a fixed layout size.
function sized(el: Element, width = 400, height = 400) {
  vi.spyOn(el, "getBoundingClientRect").mockReturnValue({
    x: 0, y: 0, left: 0, top: 0, width, height, right: width, bottom: height, toJSON: () => ({}),
  } as DOMRect);
}

describe("renderRGBA", () => {
  it("writes one RGBA pixel per cell, top row = highest y", () => {
    const map = makeMap(3, 2);
    const rgba = renderRGBA(map, [0, 5]);
    expect(rgba).toHaveLength(3 * 2 * 4);
    // Top-left pixel shows row j=1 (max y), column 0 -> value 3.
    const top = Array.from(rgba.slice(0, 4));
    const bottomLeft = Array.from(rgba.slice(12, 16)); // row j=0, column 0 -> value 0
    expect(top[3]).toBe(255);
    expect(top).not.toEqual(bottomLeft);
  });

  it("renders a 100 x 100 map within budget", () => {
    const map = makeMap(100, 100);
    const t0 = performance.now();
    for (let k = 0; k < 10; k++) renderRGBA(map, [0, 9999]);
    expect((performance.now() - t0) / 10).toBeLessThan(16);
  });
});

describe("Heatmap", () => {
  it("shows the axes gates and a placeholder without data", () => {
    render(<Heatmap map={null} onPick={vi.fn()} />);
    expect(screen.getByText(/no 2d map yet/i)).toBeInTheDocument();
  });

  it("shows a crosshair readout of voltages and current under the cursor", () => {
    render(<Heatmap map={makeMap(5, 5)} onPick={vi.fn()} />);
    const surface = screen.getByTestId("heatmap");
    sized(surface);
    fireEvent.mouseMove(surface, { clientX: 400, clientY: 0 }); // top-right corner
    const readout = screen.getByTestId("crosshair");
    expect(readout).toHaveTextContent("PA1 = -0.5800 V");
    expect(readout).toHaveTextContent("PA2 = -0.5800 V");
    expect(readout).toHaveTextContent("I = 24"); // cell (4, 4)
  });

  it("clicking sets both gate voltages at the clicked point", () => {
    const onPick = vi.fn();
    render(<Heatmap map={makeMap(5, 5)} onPick={onPick} />);
    const surface = screen.getByTestId("heatmap");
    sized(surface);
    fireEvent.click(surface, { clientX: 0, clientY: 400 }); // bottom-left corner
    expect(onPick).toHaveBeenCalledWith({ PA1: -0.66, PA2: -0.66 });
  });

  it("click mapping stays accurate after zooming in", () => {
    const onPick = vi.fn();
    render(<Heatmap map={makeMap(5, 5)} onPick={onPick} />);
    const surface = screen.getByTestId("heatmap");
    sized(surface);
    fireEvent.wheel(surface, { clientX: 200, clientY: 200, deltaY: -100 }); // zoom in 2x at centre
    fireEvent.click(surface, { clientX: 0, clientY: 0 });
    const call = onPick.mock.calls[0]?.[0] as Record<string, number>;
    expect(call.PA1).toBeCloseTo(-0.64, 10);
    expect(call.PA2).toBeCloseTo(-0.60, 10);
  });

  it("a drag pans instead of picking, and double-click resets the view", () => {
    const onPick = vi.fn();
    render(<Heatmap map={makeMap(5, 5)} onPick={onPick} />);
    const surface = screen.getByTestId("heatmap");
    sized(surface);
    fireEvent.wheel(surface, { clientX: 200, clientY: 200, deltaY: -100 });
    fireEvent.mouseDown(surface, { clientX: 200, clientY: 200 });
    fireEvent.mouseMove(surface, { clientX: 300, clientY: 200 });
    fireEvent.mouseUp(surface, { clientX: 300, clientY: 200 });
    fireEvent.click(surface, { clientX: 300, clientY: 200 });
    expect(onPick).not.toHaveBeenCalled();
    fireEvent.doubleClick(surface);
    fireEvent.click(surface, { clientX: 400, clientY: 0 });
    const last = onPick.mock.lastCall?.[0] as Record<string, number>;
    expect(last.PA1).toBeCloseTo(-0.58, 12);
    expect(last.PA2).toBeCloseTo(-0.58, 12);
  });

  it("an edge click lands exactly on the measured extent, never beyond it", () => {
    const onPick = vi.fn();
    const map = makeMap(5, 5);
    render(<Heatmap map={map} onPick={onPick} />);
    const surface = screen.getByTestId("heatmap");
    sized(surface);
    fireEvent.click(surface, { clientX: 401, clientY: -1 }); // a pixel past the corner
    expect(onPick).toHaveBeenCalledWith({ PA1: map.xs.at(-1), PA2: map.ys.at(-1) });
  });

  it("without gate labels yet (live map) clicking does nothing", () => {
    const onPick = vi.fn();
    render(<Heatmap map={{ ...makeMap(5, 5), xGate: null, yGate: null, complete: false }} onPick={onPick} />);
    const surface = screen.getByTestId("heatmap");
    sized(surface);
    fireEvent.click(surface, { clientX: 10, clientY: 10 });
    expect(onPick).not.toHaveBeenCalled();
    expect(screen.getByText(/measuring/i)).toBeInTheDocument();
  });
});
