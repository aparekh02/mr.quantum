// Perceptually uniform colour scale (viridis, 9 evenly spaced stops) and robust
// colour limits for current maps.

export type RGB = [number, number, number];

export const VIRIDIS_STOPS: readonly RGB[] = [
  [68, 1, 84],
  [71, 44, 122],
  [59, 81, 139],
  [44, 113, 142],
  [33, 144, 141],
  [39, 173, 129],
  [92, 200, 99],
  [170, 220, 50],
  [253, 231, 37],
];

const MISSING: RGB = [0, 0, 0];

export function colorAt(value: number, lo: number, hi: number): RGB {
  if (!Number.isFinite(value)) return MISSING;
  const t = hi === lo ? 0.5 : Math.min(1, Math.max(0, (value - lo) / (hi - lo)));
  const scaled = t * (VIRIDIS_STOPS.length - 1);
  const i = Math.min(Math.floor(scaled), VIRIDIS_STOPS.length - 2);
  const f = scaled - i;
  const a = VIRIDIS_STOPS[i] as RGB;
  const b = VIRIDIS_STOPS[i + 1] as RGB;
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ];
}

/** Colour limits at the given tail fraction (0.01 = 1st..99th percentile). */
export function limits(values: Float64Array, tail = 0.01): [number, number] {
  const finite = Array.from(values).filter(Number.isFinite).sort((a, b) => a - b);
  if (finite.length === 0) return [0, 1];
  const k = Math.min(Math.round(tail * finite.length), Math.floor((finite.length - 1) / 2));
  return [finite[k] as number, finite[finite.length - 1 - k] as number];
}
