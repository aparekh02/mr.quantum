import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PadInfo } from "../api/types";
import { GateSliders } from "./GateSliders";

const pads: PadInfo[] = [
  { name: "PB", pad_type: "GATE", electrode_type: "PLUNGER", v_lower_bound: -2, v_upper_bound: 0.3, controllable: true, measurable: true, group: "side_B" },
  { name: "BB0", pad_type: "GATE", electrode_type: "BARRIER", v_lower_bound: -2, v_upper_bound: 0.3, controllable: true, measurable: true, group: "side_B" },
  { name: "OUT_B", pad_type: "CONTACT", electrode_type: "DRAIN", v_lower_bound: -0.01, v_upper_bound: 0.01, controllable: false, measurable: true, group: "side_B" },
];

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("GateSliders", () => {
  it("renders one slider per controllable pad with its bounds", () => {
    render(<GateSliders pads={pads} voltages={{ PB: -0.5, BB0: 0 }} onSet={vi.fn()} />);
    const pb = screen.getByLabelText("PB") as HTMLInputElement;
    expect(pb.min).toBe("-2");
    expect(pb.max).toBe("0.3");
    expect(pb.value).toBe("-0.5");
    expect(screen.queryByLabelText("OUT_B")).toBeNull();
  });

  it("shows the dragged value immediately and sends it", async () => {
    const onSet = vi.fn().mockResolvedValue({ PB: -0.7, BB0: 0 });
    render(<GateSliders pads={pads} voltages={{ PB: -0.5, BB0: 0 }} onSet={onSet} />);
    await act(async () => {
      fireEvent.change(screen.getByLabelText("PB"), { target: { value: "-0.7" } });
    });
    expect(onSet).toHaveBeenCalledWith({ PB: -0.7 });
    expect(screen.getByTestId("value-PB")).toHaveTextContent("-0.700 V");
  });

  it("keeps one request in flight and sends only the newest queued value", async () => {
    const first = deferred<Record<string, number>>();
    const onSet = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockResolvedValue({ PB: -0.9, BB0: 0 });
    render(<GateSliders pads={pads} voltages={{ PB: -0.5, BB0: 0 }} onSet={onSet} />);
    const slider = screen.getByLabelText("PB");
    await act(async () => {
      fireEvent.change(slider, { target: { value: "-0.6" } });
      fireEvent.change(slider, { target: { value: "-0.8" } });
      fireEvent.change(slider, { target: { value: "-0.9" } });
    });
    expect(onSet).toHaveBeenCalledTimes(1);
    await act(async () => {
      first.resolve({ PB: -0.6, BB0: 0 });
    });
    expect(onSet).toHaveBeenCalledTimes(2);
    expect(onSet).toHaveBeenLastCalledWith({ PB: -0.9 });
    expect(screen.getByTestId("value-PB")).toHaveTextContent("-0.900 V");
  });

  it("reverts to the server value and shows the error when a set fails", async () => {
    const onSet = vi.fn().mockRejectedValue(new Error("outside bounds"));
    render(<GateSliders pads={pads} voltages={{ PB: -0.5, BB0: 0 }} onSet={onSet} />);
    await act(async () => {
      fireEvent.change(screen.getByLabelText("PB"), { target: { value: "-0.7" } });
    });
    expect(screen.getByTestId("value-PB")).toHaveTextContent("-0.500 V");
    expect(screen.getByRole("alert")).toHaveTextContent("outside bounds");
  });

  it("follows voltages changed elsewhere (e.g. by a routine)", () => {
    const { rerender } = render(<GateSliders pads={pads} voltages={{ PB: -0.5, BB0: 0 }} onSet={vi.fn()} />);
    rerender(<GateSliders pads={pads} voltages={{ PB: -1.1, BB0: 0 }} onSet={vi.fn()} />);
    expect(screen.getByTestId("value-PB")).toHaveTextContent("-1.100 V");
  });

  it("disables sliders while disabled", () => {
    render(<GateSliders pads={pads} voltages={{ PB: 0, BB0: 0 }} onSet={vi.fn()} disabled />);
    expect(screen.getByLabelText("PB")).toBeDisabled();
  });
});
