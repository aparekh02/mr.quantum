import { type MouseEvent, useEffect, useMemo, useRef, useState, type WheelEvent } from "react";
import type { MapData } from "../state/maps";
import { colorAt, limits } from "../viz/colormap";
import { clampToBounds, fullView, pan, pixelToData, type Size, type Viewport, zoomAt } from "../viz/viewport";

/** RGBA pixels, one per cell, x ascending left to right, y descending top to bottom. */
export function renderRGBA(map: MapData, [lo, hi]: [number, number]): Uint8ClampedArray {
  const nx = map.xs.length;
  const ny = map.ys.length;
  const out = new Uint8ClampedArray(nx * ny * 4);
  for (let r = 0; r < ny; r++) {
    const j = ny - 1 - r;
    for (let i = 0; i < nx; i++) {
      const [cr, cg, cb] = colorAt(map.values[j * nx + i] ?? Number.NaN, lo, hi);
      const o = (r * nx + i) * 4;
      out[o] = cr;
      out[o + 1] = cg;
      out[o + 2] = cb;
      out[o + 3] = 255;
    }
  }
  return out;
}

function nearest(axis: number[], v: number): number {
  let best = 0;
  for (let k = 1; k < axis.length; k++) {
    if (Math.abs((axis[k] as number) - v) < Math.abs((axis[best] as number) - v)) best = k;
  }
  return best;
}

const DRAG_THRESHOLD = 3;
export const COLOUR_TAIL = 0.002;
const CANVAS = 480;

interface Props {
  map: MapData | null;
  onPick: (voltages: Record<string, number>) => void;
}

export function Heatmap({ map, onPick }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const bounds = useMemo<Viewport | null>(() => {
    if (!map || map.xs.length < 2 || map.ys.length < 2) return null;
    return fullView(
      [map.xs[0] as number, map.xs.at(-1) as number],
      [map.ys[0] as number, map.ys.at(-1) as number],
    );
  }, [map]);
  const [view, setView] = useState<Viewport | null>(bounds);
  const [cursor, setCursor] = useState<{ x: number; y: number; i: number; j: number } | null>(null);
  const drag = useRef<{ x: number; y: number; view: Viewport; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const [renderMs, setRenderMs] = useState<number | null>(null);

  useEffect(() => setView(bounds), [bounds]);

  // Clip only a few outlier pixels: on transport maps the brightest features (triple
  // points) are the physics, and heavier clipping makes them look like the lines.
  const colour = useMemo(() => (map ? limits(map.values, COLOUR_TAIL) : ([0, 1] as [number, number])), [map]);

  useEffect(() => {
    const el = canvas.current;
    if (!el || !map || !view || !bounds) return;
    let ctx: CanvasRenderingContext2D | null = null;
    try {
      ctx = el.getContext("2d");
    } catch {
      ctx = null;
    }
    if (!ctx) return;
    const t0 = performance.now();
    const nx = map.xs.length;
    const ny = map.ys.length;
    const image = new ImageData(renderRGBA(map, colour) as Uint8ClampedArray<ArrayBuffer>, nx, ny);
    const off = document.createElement("canvas");
    off.width = nx;
    off.height = ny;
    off.getContext("2d")?.putImageData(image, 0, 0);
    // Source rectangle of the cell image that the current view shows.
    const sx = ((view.x0 - bounds.x0) / (bounds.x1 - bounds.x0)) * nx;
    const sw = ((view.x1 - view.x0) / (bounds.x1 - bounds.x0)) * nx;
    const sy = ((bounds.y1 - view.y1) / (bounds.y1 - bounds.y0)) * ny;
    const sh = ((view.y1 - view.y0) / (bounds.y1 - bounds.y0)) * ny;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, CANVAS, CANVAS);
    ctx.drawImage(off, sx, sy, sw, sh, 0, 0, CANVAS, CANVAS);
    setRenderMs(performance.now() - t0);
  }, [map, view, bounds, colour]);

  if (!map || !bounds || !view) {
    return <p className="heatmap-empty">No 2D map yet. Run charge_stability_diagram.</p>;
  }

  const size = (el: HTMLElement): { size: Size; left: number; top: number } => {
    const r = el.getBoundingClientRect();
    return { size: { width: r.width, height: r.height }, left: r.left, top: r.top };
  };

  const locate = (e: MouseEvent<HTMLElement>, v: Viewport) => {
    const { size: s, left, top } = size(e.currentTarget);
    const px = e.clientX - left;
    const py = e.clientY - top;
    return { ...pixelToData(px, py, v, s), px, py, s };
  };

  function onMove(e: MouseEvent<HTMLCanvasElement>): void {
    const d = drag.current;
    if (d && view) {
      const dx = e.clientX - d.x;
      const dy = e.clientY - d.y;
      if (Math.abs(dx) + Math.abs(dy) > DRAG_THRESHOLD) d.moved = true;
      if (d.moved && bounds) setView(clampToBounds(pan(d.view, dx, dy, size(e.currentTarget).size), bounds));
      return;
    }
    if (!view || !map) return;
    const p = locate(e, view);
    setCursor({ x: p.x, y: p.y, i: nearest(map.xs, p.x), j: nearest(map.ys, p.y) });
  }

  function onClick(e: MouseEvent<HTMLCanvasElement>): void {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    if (!view || !bounds || !map?.xGate || !map.yGate) return;
    const p = locate(e, view);
    // Clamp to the measured extent: an edge click must never step past a gate bound.
    const x = Math.min(Math.max(p.x, bounds.x0), bounds.x1);
    const y = Math.min(Math.max(p.y, bounds.y0), bounds.y1);
    onPick({ [map.xGate]: x, [map.yGate]: y });
  }

  function onWheel(e: WheelEvent<HTMLCanvasElement>): void {
    if (!view || !bounds) return;
    const { size: s, left, top } = size(e.currentTarget);
    const factor = 2 ** (-e.deltaY / 100);
    setView(clampToBounds(zoomAt(view, e.clientX - left, e.clientY - top, factor, s), bounds));
  }

  const value = cursor ? map.value(cursor.i, cursor.j) : Number.NaN;
  return (
    <figure className="heatmap">
      <figcaption>
        {map.title} {!map.complete && <span className="trace-live">● measuring</span>}
      </figcaption>
      <canvas
        ref={canvas}
        data-testid="heatmap"
        data-cells={map.xs.length * map.ys.length}
        data-render-ms={renderMs === null ? undefined : renderMs.toFixed(2)}
        width={CANVAS}
        height={CANVAS}
        onMouseMove={onMove}
        onMouseLeave={() => setCursor(null)}
        onMouseDown={(e) => {
          if (view) drag.current = { x: e.clientX, y: e.clientY, view, moved: false };
        }}
        onMouseUp={() => {
          suppressClick.current = drag.current?.moved ?? false;
          drag.current = null;
        }}
        onClick={onClick}
        onWheel={onWheel}
        onDoubleClick={() => setView(bounds)}
      />
      <p data-testid="crosshair" className="crosshair">
        {cursor && (
          <>
            {map.xGate ?? "x"} = {cursor.x.toFixed(4)} V, {map.yGate ?? "y"} = {cursor.y.toFixed(4)} V, I ={" "}
            {Number.isFinite(value) ? `${value.toPrecision(3)} A` : "—"}
          </>
        )}
      </p>
    </figure>
  );
}
