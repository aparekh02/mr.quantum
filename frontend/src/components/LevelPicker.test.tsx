import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { LevelInfo } from "../api/types";
import { LevelPanel } from "./LevelPanel";

const make = (order: number, id: string, title: string): LevelInfo => ({
  id, order, title, concept: `Concept of ${title}.`, objective: `Objective of ${title}.`,
  device: "dqd_with_sensor", hint_count: 1, measurement_budget: 1000,
});
const levels = [
  make(1, "coulomb-peak", "Find the Coulomb peak"),
  make(2, "compensate-sensor", "Compensate the sensor"),
  make(3, "double-dot", "Find the double dot"),
];

describe("LevelPanel picker", () => {
  it("offers every level and shows the first by default", () => {
    render(<LevelPanel levels={levels} attempt={null} onStart={vi.fn()} onHint={vi.fn()} onSubmit={vi.fn()} busy={false} />);
    const picker = screen.getByLabelText("Level") as HTMLSelectElement;
    expect(Array.from(picker.options).map((o) => o.value)).toEqual(["coulomb-peak", "compensate-sensor", "double-dot"]);
    expect(screen.getByText("1. Find the Coulomb peak")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Start level" })).toHaveLength(1);
  });

  it("starts the chosen level and shows its concept", async () => {
    const onStart = vi.fn().mockResolvedValue(undefined);
    render(<LevelPanel levels={levels} attempt={null} onStart={onStart} onHint={vi.fn()} onSubmit={vi.fn()} busy={false} />);
    await userEvent.selectOptions(screen.getByLabelText("Level"), "double-dot");
    expect(screen.getByText("Concept of Find the double dot.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start level" }));
    expect(onStart).toHaveBeenCalledWith("double-dot");
  });
});
