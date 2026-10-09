import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { RoutineInfo } from "../api/types";
import { RunPanel, templateFor } from "./RunPanel";

const routines: RoutineInfo[] = [
  {
    name: "noise_floor_measurement",
    parameters: [
      { name: "measure_electrode", type: "str", required: true, default: null },
      { name: "num_points", type: "int", required: false, default: 100 },
    ],
  },
  { name: "leakage_test", parameters: [{ name: "leakage_threshold_resistance", type: "int", required: true, default: null }] },
];

describe("RunPanel", () => {
  it("templates the required parameters", () => {
    expect(templateFor(routines[0]!)).toBe('{\n  "measure_electrode": null\n}');
  });

  it("runs the selected routine with the edited parameters", async () => {
    const onRun = vi.fn().mockResolvedValue(undefined);
    render(<RunPanel routines={routines} onRun={onRun} running={false} />);
    const params = screen.getByLabelText("Parameters (JSON)");
    fireEvent.change(params, { target: { value: '{"measure_electrode": "OUT_B"}' } });
    await userEvent.click(screen.getByRole("button", { name: "Run routine" }));
    expect(onRun).toHaveBeenCalledWith("noise_floor_measurement", { measure_electrode: "OUT_B" });
  });

  it("switching routine resets the template", async () => {
    render(<RunPanel routines={routines} onRun={vi.fn()} running={false} />);
    await userEvent.selectOptions(screen.getByLabelText("Routine"), "leakage_test");
    expect((screen.getByLabelText("Parameters (JSON)") as HTMLTextAreaElement).value).toContain(
      "leakage_threshold_resistance",
    );
  });

  it("rejects invalid JSON without calling the API", async () => {
    const onRun = vi.fn();
    render(<RunPanel routines={routines} onRun={onRun} running={false} />);
    fireEvent.change(screen.getByLabelText("Parameters (JSON)"), { target: { value: "{oops" } });
    await userEvent.click(screen.getByRole("button", { name: "Run routine" }));
    expect(onRun).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("not valid JSON");
  });

  it("rejects JSON that is not an object", async () => {
    const onRun = vi.fn();
    render(<RunPanel routines={routines} onRun={onRun} running={false} />);
    fireEvent.change(screen.getByLabelText("Parameters (JSON)"), { target: { value: "[1]" } });
    await userEvent.click(screen.getByRole("button", { name: "Run routine" }));
    expect(onRun).not.toHaveBeenCalled();
  });

  it("shows API errors from the run", async () => {
    const onRun = vi.fn().mockRejectedValue(new Error("422: unknown group"));
    render(<RunPanel routines={routines} onRun={onRun} running={false} />);
    fireEvent.change(screen.getByLabelText("Parameters (JSON)"), { target: { value: "{}" } });
    await userEvent.click(screen.getByRole("button", { name: "Run routine" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("unknown group");
  });

  it("disables the button while a routine runs", () => {
    render(<RunPanel routines={routines} onRun={vi.fn()} running />);
    expect(screen.getByRole("button", { name: "Running…" })).toBeDisabled();
  });
});
