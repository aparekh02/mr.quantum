import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PadInfo } from "../api/types";
import { CsdPanel } from "./CsdPanel";

const gate = (name: string, electrode_type: string): PadInfo => ({
  name, pad_type: "GATE", electrode_type, v_lower_bound: -2, v_upper_bound: 0.3,
  controllable: true, measurable: true, group: "side_A",
});
const pads: PadInfo[] = [
  gate("BA0", "BARRIER"),
  gate("PA1", "PLUNGER"),
  gate("PA2", "PLUNGER"),
  { name: "OUT_A", pad_type: "CONTACT", electrode_type: "DRAIN", v_lower_bound: null, v_upper_bound: null, controllable: false, measurable: true, group: "side_A" },
];

describe("CsdPanel", () => {
  it("defaults to the first two plungers around their present voltages", async () => {
    const onRun = vi.fn().mockResolvedValue(undefined);
    render(<CsdPanel pads={pads} voltages={{ PA1: -0.62, PA2: -0.6 }} onRun={onRun} running={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Measure map" }));
    const [routine, params] = onRun.mock.calls[0] as [string, Record<string, unknown>];
    expect(routine).toBe("charge_stability_diagram");
    expect(params).toMatchObject({ gate_x: "PA1", gate_y: "PA2", points: 48, measure_electrode: "OUT_A" });
    expect(params.x_range).toEqual([-0.66, -0.58]);
    expect(params.y_range).toEqual([-0.64, -0.56]);
  });

  it("clamps the default window to the gate bounds", async () => {
    const onRun = vi.fn().mockResolvedValue(undefined);
    render(<CsdPanel pads={pads} voltages={{ PA1: 0.29, PA2: -1.99 }} onRun={onRun} running={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Measure map" }));
    const params = onRun.mock.calls[0]?.[1] as Record<string, number[]>;
    expect(params.x_range).toEqual([0.25, 0.3]);
    expect(params.y_range).toEqual([-2, -1.95]);
  });

  it("uses the edited gates, ranges and resolution", async () => {
    const onRun = vi.fn().mockResolvedValue(undefined);
    render(<CsdPanel pads={pads} voltages={{}} onRun={onRun} running={false} />);
    await userEvent.selectOptions(screen.getByLabelText("X gate"), "BA0");
    fireEvent.change(screen.getByLabelText("X from (V)"), { target: { value: "-1" } });
    fireEvent.change(screen.getByLabelText("X to (V)"), { target: { value: "-0.5" } });
    fireEvent.change(screen.getByLabelText("Points per axis"), { target: { value: "100" } });
    await userEvent.click(screen.getByRole("button", { name: "Measure map" }));
    expect(onRun.mock.calls[0]?.[1]).toMatchObject({ gate_x: "BA0", x_range: [-1, -0.5], points: 100 });
  });

  it("refuses the same gate on both axes", async () => {
    const onRun = vi.fn();
    render(<CsdPanel pads={pads} voltages={{}} onRun={onRun} running={false} />);
    await userEvent.selectOptions(screen.getByLabelText("X gate"), "PA2");
    await userEvent.click(screen.getByRole("button", { name: "Measure map" }));
    expect(onRun).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("different gates");
  });

  it("shows API errors", async () => {
    const onRun = vi.fn().mockRejectedValue(new Error("422: points must be in [2, 256]"));
    render(<CsdPanel pads={pads} voltages={{}} onRun={onRun} running={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Measure map" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("points must be");
  });

  it("is disabled while a routine runs", () => {
    render(<CsdPanel pads={pads} voltages={{}} onRun={vi.fn()} running />);
    expect(screen.getByRole("button", { name: "Measure map" })).toBeDisabled();
  });
});
