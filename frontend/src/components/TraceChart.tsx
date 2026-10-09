import type { Trace } from "../state/traces";

const W = 640;
const H = 320;
const M = { left: 70, right: 16, top: 28, bottom: 44 };

function extent(values: number[]): [number, number] {
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  if (lo === hi) {
    const pad = Math.abs(lo) * 0.1 || 1;
    return [lo - pad, hi + pad];
  }
  return [lo, hi];
}

const fmt = (v: number) => v.toPrecision(3);

export function TraceChart({ trace }: { trace: Trace | null }) {
  if (!trace || trace.points.length === 0) {
    return <p className="trace-empty">No data yet. Run a routine to see its sweeps here.</p>;
  }
  const [x0, x1] = extent(trace.points.map((p) => p.x));
  const [y0, y1] = extent(trace.points.map((p) => p.y));
  const sx = (x: number) => M.left + ((x - x0) / (x1 - x0)) * (W - M.left - M.right);
  const sy = (y: number) => H - M.bottom - ((y - y0) / (y1 - y0)) * (H - M.top - M.bottom);
  const coords = trace.points.map((p) => `${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");

  return (
    <figure className="trace">
      <svg
        data-testid="trace"
        data-points={trace.points.length}
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={trace.title}
      >
        <text x={M.left} y={18} className="trace-title">
          {trace.title}
        </text>
        {!trace.complete && (
          <text x={W - M.right} y={18} textAnchor="end" className="trace-live">
            ● live
          </text>
        )}
        <rect
          x={M.left}
          y={M.top}
          width={W - M.left - M.right}
          height={H - M.top - M.bottom}
          className="trace-frame"
        />
        <polyline points={coords} className="trace-line" fill="none" />
        <text x={M.left} y={H - 26} className="tick">
          {fmt(x0)}
        </text>
        <text x={W - M.right} y={H - 26} textAnchor="end" className="tick">
          {fmt(x1)}
        </text>
        <text x={M.left - 6} y={H - M.bottom} textAnchor="end" className="tick">
          {fmt(y0)}
        </text>
        <text x={M.left - 6} y={M.top + 10} textAnchor="end" className="tick">
          {fmt(y1)}
        </text>
        <text x={(W + M.left) / 2} y={H - 8} textAnchor="middle" className="axis-label">
          {trace.xLabel}
        </text>
        <text
          x={14}
          y={(H - M.bottom + M.top) / 2}
          textAnchor="middle"
          transform={`rotate(-90 14 ${(H - M.bottom + M.top) / 2})`}
          className="axis-label"
        >
          {trace.yLabel}
        </text>
      </svg>
    </figure>
  );
}
