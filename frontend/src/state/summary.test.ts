import { describe, expect, it } from "vitest";
import { formatVolts, summarize } from "./summary";

describe("summarize", () => {
  it("keeps small results readable and abbreviates long arrays", () => {
    const text = summarize({
      compensation_gradients: { PA1: -0.10172345678, PA2: -0.15 },
      trace: Array.from({ length: 100 }, (_, i) => i),
      nested: { grid: [[1, 2], [3, 4]] },
    });
    const parsed = JSON.parse(text);
    expect(parsed.compensation_gradients.PA1).toBe(-0.101723);
    expect(parsed.trace).toBe("[100 values]");
    expect(parsed.nested.grid).toEqual([[1, 2], [3, 4]]);
  });

  it("handles scalars, null and strings", () => {
    expect(summarize(null)).toBe("null");
    expect(summarize("done")).toBe('"done"');
    expect(summarize(0.000012345678)).toBe("0.0000123457");
  });
});

describe("formatVolts", () => {
  it("shows millivolt precision, and a fourth decimal only when needed", () => {
    expect(formatVolts(-0.7)).toBe("-0.700 V");
    expect(formatVolts(-0.6329)).toBe("-0.6329 V");
    expect(formatVolts(-0.64003)).toBe("-0.640 V");
    expect(formatVolts(0)).toBe("0.000 V");
  });
});
