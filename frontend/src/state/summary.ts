// Readable summaries of routine results and voltages for the UI.

const MAX_ARRAY = 8;

function abbreviate(value: unknown): unknown {
  if (typeof value === "number") return Number.isFinite(value) ? Number(value.toPrecision(6)) : value;
  if (Array.isArray(value)) {
    if (value.length > MAX_ARRAY) return `[${value.length} values]`;
    return value.map(abbreviate);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, abbreviate(v)]));
  }
  return value;
}

/** Pretty JSON with long arrays collapsed and numbers at 6 significant figures. */
export function summarize(result: unknown): string {
  return JSON.stringify(abbreviate(result), null, 2) ?? "null";
}

/** Millivolt precision, plus a fourth decimal when it carries information. */
export function formatVolts(v: number): string {
  const four = v.toFixed(4);
  const text = four.endsWith("0") ? v.toFixed(3) : four;
  return `${text === "-0.000" ? "0.000" : text} V`;
}
