// Pan/zoom geometry for the heatmap. A viewport is the visible rectangle in data
// units (volts); pixel (0, 0) is the top-left, i.e. minimum x and maximum y.

export interface Viewport {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

export interface Size {
  width: number;
  height: number;
}

export function fullView(xRange: [number, number], yRange: [number, number]): Viewport {
  return {
    x0: Math.min(...xRange),
    x1: Math.max(...xRange),
    y0: Math.min(...yRange),
    y1: Math.max(...yRange),
  };
}

export function pixelToData(px: number, py: number, v: Viewport, size: Size) {
  return {
    x: v.x0 + (px / size.width) * (v.x1 - v.x0),
    y: v.y1 - (py / size.height) * (v.y1 - v.y0),
  };
}

export function dataToPixel(x: number, y: number, v: Viewport, size: Size) {
  return {
    px: ((x - v.x0) / (v.x1 - v.x0)) * size.width,
    py: ((v.y1 - y) / (v.y1 - v.y0)) * size.height,
  };
}

/** Zoom by ``factor`` (> 1 zooms in) keeping the point under the cursor fixed. */
export function zoomAt(v: Viewport, px: number, py: number, factor: number, size: Size): Viewport {
  const anchor = pixelToData(px, py, v, size);
  const fx = px / size.width;
  const fy = py / size.height;
  const w = (v.x1 - v.x0) / factor;
  const h = (v.y1 - v.y0) / factor;
  const x0 = anchor.x - fx * w;
  const y1 = anchor.y + fy * h;
  return { x0, x1: x0 + w, y0: y1 - h, y1 };
}

/** Drag the content by (dx, dy) pixels. */
export function pan(v: Viewport, dx: number, dy: number, size: Size): Viewport {
  const sx = (dx / size.width) * (v.x1 - v.x0);
  const sy = (dy / size.height) * (v.y1 - v.y0);
  return { x0: v.x0 - sx, x1: v.x1 - sx, y0: v.y0 + sy, y1: v.y1 + sy };
}

/** Keep the view inside the data; it can never be larger than the data. */
export function clampToBounds(v: Viewport, bounds: Viewport): Viewport {
  const fit = (lo: number, hi: number, blo: number, bhi: number): [number, number] => {
    const span = Math.min(hi - lo, bhi - blo);
    let a = lo;
    if (a < blo) a = blo;
    if (a + span > bhi) a = bhi - span;
    return [a, a + span];
  };
  const [x0, x1] = fit(v.x0, v.x1, bounds.x0, bounds.x1);
  const [y0, y1] = fit(v.y0, v.y1, bounds.y0, bounds.y1);
  return { x0, x1, y0, y1 };
}
