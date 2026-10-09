import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TraceChart } from "./TraceChart";

describe("TraceChart", () => {
  it("shows a placeholder without data", () => {
    render(<TraceChart trace={null} />);
    expect(screen.getByText(/no data yet/i)).toBeInTheDocument();
  });

  it("renders every point and the axis labels", () => {
    const points = Array.from({ length: 50 }, (_, i) => ({ x: i / 10, y: Math.sin(i) * 1e-9 }));
    render(
      <TraceChart
        trace={{ key: "k", title: "r: sweep", xLabel: "Voltage", yLabel: "Current", points, complete: true }}
      />,
    );
    const chart = screen.getByTestId("trace");
    expect(chart).toHaveAttribute("data-points", "50");
    expect(chart.querySelector("polyline")?.getAttribute("points")?.split(" ")).toHaveLength(50);
    expect(screen.getByText("Voltage")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText("r: sweep")).toBeInTheDocument();
  });

  it("handles a single point and a flat trace without NaN coordinates", () => {
    render(
      <TraceChart
        trace={{ key: "k", title: "t", xLabel: "V", yLabel: "I", points: [{ x: 1, y: 2 }], complete: false }}
      />,
    );
    const coords = screen.getByTestId("trace").querySelector("polyline")?.getAttribute("points") ?? "";
    expect(coords).not.toContain("NaN");
    expect(screen.getByText(/live/i)).toBeInTheDocument();
  });
});
