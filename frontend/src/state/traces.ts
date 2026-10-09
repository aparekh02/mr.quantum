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

const is2D = (x: unknown): boolean => Array.isArray(x) && x.length === 2;

/** Apply a batch of events. Live points are appended into one array per batch,
 * so a long sweep costs linear time however it is batched. */
export function applyEvents(state: TraceState, events: TrainerEvent[]): TraceState {
  let latest = state.latest;
  let completed = state.completed;
  let owned = false; // whether latest.points is a fresh array we may push into
  let changed = false;

  for (const event of events) {
    const key = `${event.routine ?? ""}/${event.name}`;
    const title = `${event.routine ?? "manual"}: ${event.name}`;
    const data = (event.data ?? {}) as Record<string, unknown>;

    if (event.kind === "sweep_point") {
      if (is2D(data.x)) continue; // 2D maps are the heatmap's job
      const point = zip(axis((data.x as unknown[]) ?? []).slice(0, 1), ((data.y as unknown[]) ?? []).slice(0, 1));
      if (!latest || latest.key !== key || latest.complete) {
        latest = { key, title, xLabel: "", yLabel: "", points: [], complete: false };
        owned = true;
      } else if (!owned) {
        latest = { ...latest, points: [...latest.points] };
        owned = true;
      }
      latest.points.push(...point);
      changed = true;
    } else if (event.kind === "sweep") {
      if (Array.isArray(data.x_label)) continue; // 2D sweep
      latest = {
        key,
        title,
        xLabel: String(data.x_label ?? ""),
        yLabel: String(data.y_label ?? ""),
        points: zip(axis((data.x_data as unknown[]) ?? []), (data.y_data as unknown[]) ?? []),
        complete: true,
      };
      owned = false;
      completed = [...completed, latest].slice(-KEEP);
      changed = true;
    }
  }
  return changed ? { latest, completed } : state;
}

export function applyEvent(state: TraceState, event: TrainerEvent): TraceState {
  return applyEvents(state, [event]);
}
