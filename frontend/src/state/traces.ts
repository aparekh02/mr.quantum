import type { TrainerEvent } from "../api/types";

export interface Point {
  x: number;
  y: number;
}

export interface Trace {
  key: string;
  title: string;
  xLabel: string;
  yLabel: string;
  points: Point[];
  complete: boolean;
}

export interface TraceState {
  latest: Trace | null;
  completed: Trace[];
}

export const emptyTraces: TraceState = { latest: null, completed: [] };

const KEEP = 20;

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function axis(x: unknown[]): number[] {
  // Plot an n-gate sweep against the coordinate that varies the most.
  const rows = x.map((row) => (Array.isArray(row) ? row : [row]));
  const width = Math.max(0, ...rows.map((r) => r.length));
  let best = 0;
  let bestRange = -1;
  for (let i = 0; i < width; i++) {
    const values = rows.map((r) => r[i]).filter(finite);
    const range = values.length ? Math.max(...values) - Math.min(...values) : -1;
    if (range > bestRange) {
      best = i;
      bestRange = range;
    }
  }
  return rows.map((r) => (finite(r[best]) ? r[best] : Number.NaN));
}

function zip(xs: number[], ys: unknown[]): Point[] {
  return xs.flatMap((x, i) => {
    const y = ys[i];
    return finite(x) && finite(y) ? [{ x, y }] : [];
  });
}

export function applyEvent(state: TraceState, event: TrainerEvent): TraceState {
  const key = `${event.routine ?? ""}/${event.name}`;
  const title = `${event.routine ?? "manual"}: ${event.name}`;
  const data = (event.data ?? {}) as Record<string, unknown>;

  if (event.kind === "sweep_point") {
    const xs = axis((data.x as unknown[]) ?? []).slice(0, 1);
    const point = zip(xs, ((data.y as unknown[]) ?? []).slice(0, 1));
    const live =
      state.latest && state.latest.key === key && !state.latest.complete
        ? state.latest
        : { key, title, xLabel: "", yLabel: "", points: [], complete: false };
    return { ...state, latest: { ...live, points: [...live.points, ...point] } };
  }

  if (event.kind === "sweep") {
    const trace: Trace = {
      key,
      title,
      xLabel: String(data.x_label ?? ""),
      yLabel: String(data.y_label ?? ""),
      points: zip(axis((data.x_data as unknown[]) ?? []), (data.y_data as unknown[]) ?? []),
      complete: true,
    };
    return { latest: trace, completed: [...state.completed, trace].slice(-KEEP) };
  }

  return state;
}
