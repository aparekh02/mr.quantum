import type { TrainerEvent } from "../api/types";

// Builds 2D current maps from streamed 2D sweep points. Points accumulate in
// place (no copying per event) and the grid is rebuilt lazily when read, so a
// 10,000-point map streams without quadratic work.

export interface MapData {
  key: string;
  title: string;
  /** Gate on the horizontal axis (upstream's inner/fast gate). Null while live. */
  xGate: string | null;
  /** Gate on the vertical axis (upstream's outer/slow gate). Null while live. */
  yGate: string | null;
  xs: number[];
  ys: number[];
  /** Row-major, row j = ys[j], column i = xs[i]; NaN where unmeasured. */
  values: Float64Array;
  complete: boolean;
  value: (i: number, j: number) => number;
}

const keyOf = (v: number) => v.toPrecision(12);

function uniqueSorted(values: number[]): number[] {
  const seen = new Map<string, number>();
  for (const v of values) seen.set(keyOf(v), v);
  return [...seen.values()].sort((a, b) => a - b);
}

export class MapAccumulator {
  version = 0;
  private key: string | null = null;
  private title = "";
  private outer: number[] = [];
  private inner: number[] = [];
  private current: number[] = [];
  private labels: [string, string] | null = null;
  private complete = false;
  private cache: { version: number; map: MapData | null } = { version: -1, map: null };

  apply(event: TrainerEvent): void {
    const data = (event.data ?? {}) as Record<string, unknown>;
    const key = `${event.routine ?? ""}/${event.name}`;
    if (event.kind === "sweep_point") {
      const x = data.x as unknown[] | undefined;
      const y = data.y as unknown[] | undefined;
      if (!Array.isArray(x) || x.length !== 2 || !Array.isArray(y)) return;
      if (this.key !== key || this.complete) this.reset(key, event);
      this.push(Number(x[0]), Number(x[1]), Number(y[0]));
      this.version += 1;
    } else if (event.kind === "sweep") {
      const labels = data.x_label;
      if (!Array.isArray(labels) || labels.length !== 2) return;
      const xData = (data.x_data as unknown[][]) ?? [];
      const yData = (data.y_data as unknown[]) ?? [];
      this.reset(key, event);
      xData.forEach((row, k) => this.push(Number(row[0]), Number(row[1]), Number(yData[k])));
      this.labels = [String(labels[0]), String(labels[1])];
      this.complete = true;
      this.version += 1;
    }
  }

  latest(): MapData | null {
    if (this.cache.version === this.version) return this.cache.map;
    const map = this.key === null ? null : this.build();
    this.cache = { version: this.version, map };
    return map;
  }

  private reset(key: string, event: TrainerEvent): void {
    this.key = key;
    this.title = `${event.routine ?? "manual"}: ${event.name}`;
    this.outer = [];
    this.inner = [];
    this.current = [];
    this.labels = null;
    this.complete = false;
  }

  private push(outer: number, inner: number, value: number): void {
    this.outer.push(outer);
    this.inner.push(inner);
    this.current.push(value);
  }

  private build(): MapData {
    const xs = uniqueSorted(this.inner);
    const ys = uniqueSorted(this.outer);
    const xi = new Map(xs.map((v, i) => [keyOf(v), i]));
    const yi = new Map(ys.map((v, j) => [keyOf(v), j]));
    const values = new Float64Array(xs.length * ys.length).fill(Number.NaN);
    for (let k = 0; k < this.current.length; k++) {
      const i = xi.get(keyOf(this.inner[k] as number));
      const j = yi.get(keyOf(this.outer[k] as number));
      if (i !== undefined && j !== undefined) values[j * xs.length + i] = this.current[k] as number;
    }
    const nx = xs.length;
    return {
      key: this.key ?? "",
      title: this.title,
      xGate: this.labels ? this.labels[1] : null,
      yGate: this.labels ? this.labels[0] : null,
      xs,
      ys,
      values,
      complete: this.complete,
      value: (i, j) => values[j * nx + i] ?? Number.NaN,
    };
  }
}
