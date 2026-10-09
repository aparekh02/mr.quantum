import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AttemptInfo, LevelInfo } from "../api/types";
import { LevelPanel } from "./LevelPanel";

const level: LevelInfo = {
  id: "coulomb-peak",
  order: 1,
  title: "Find the Coulomb peak",
  concept: "Coulomb blockade: a dot conducts only at charge transitions.",
  objective: "Park PB on a peak flank and submit.",
  device: "dqd_with_sensor",
  hint_count: 2,
  measurement_budget: 2500,
};
const active: AttemptInfo = {
  id: "a1", level_id: "coulomb-peak", session_id: "s1", status: "active",
  measurements: 120, hints_shown: 0, evaluation: null,
};

describe("LevelPanel", () => {
  it("lists levels with their concept and starts one", async () => {
    const onStart = vi.fn().mockResolvedValue(undefined);
    render(<LevelPanel levels={[level]} attempt={null} onStart={onStart} onHint={vi.fn()} onSubmit={vi.fn()} busy={false} />);
    expect(screen.getByText("1. Find the Coulomb peak")).toBeInTheDocument();
    expect(screen.getByText(/Coulomb blockade/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start level" }));
    expect(onStart).toHaveBeenCalledWith("coulomb-peak");
  });

  it("shows the objective, the measurement count against the budget, and hints", async () => {
    const onHint = vi
      .fn()
      .mockResolvedValueOnce("First hint")
      .mockResolvedValueOnce("Second hint")
      .mockResolvedValueOnce(null);
    render(<LevelPanel levels={[level]} attempt={active} onStart={vi.fn()} onHint={onHint} onSubmit={vi.fn()} busy={false} />);
    expect(screen.getByText(level.objective)).toBeInTheDocument();
    expect(screen.getByTestId("measurements")).toHaveTextContent("120 / 2500 measurements");
    const button = screen.getByRole("button", { name: "Show a hint" });
    await userEvent.click(button);
    await userEvent.click(button);
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["First hint", "Second hint"]);
    expect(button).toBeDisabled(); // both hints shown
  });

  it("submits and shows a successful result", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <LevelPanel levels={[level]} attempt={active} onStart={vi.fn()} onHint={vi.fn()} onSubmit={onSubmit} busy={false} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(onSubmit).toHaveBeenCalledOnce();
    rerender(
      <LevelPanel
        levels={[level]}
        attempt={{
          ...active,
          status: "submitted",
          evaluation: { success: true, accuracy: 0.97, score: 874, measurements: 900, feedback: ["On the flank."] },
        }}
        onStart={vi.fn()}
        onHint={vi.fn()}
        onSubmit={onSubmit}
        busy={false}
      />,
    );
    expect(screen.getByTestId("result")).toHaveTextContent("Level complete");
    expect(screen.getByTestId("result")).toHaveTextContent("874 points");
    expect(screen.getByTestId("result")).toHaveTextContent("97% accuracy");
    expect(screen.getByText("On the flank.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit" })).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("shows feedback for a failed attempt", () => {
    render(
      <LevelPanel
        levels={[level]}
        attempt={{
          ...active,
          status: "submitted",
          evaluation: { success: false, accuracy: 0, score: 0, measurements: 3, feedback: ["You are in a blockade valley."] },
        }}
        onStart={vi.fn()}
        onHint={vi.fn()}
        onSubmit={vi.fn()}
        busy={false}
      />,
    );
    expect(screen.getByTestId("result")).toHaveTextContent("Not yet");
    expect(screen.getByText("You are in a blockade valley.")).toBeInTheDocument();
  });

  it("cannot submit while a routine runs", () => {
    render(<LevelPanel levels={[level]} attempt={active} onStart={vi.fn()} onHint={vi.fn()} onSubmit={vi.fn()} busy />);
    expect(screen.getByRole("button", { name: "Submit" })).toBeDisabled();
  });

  it("shows errors from starting or submitting", async () => {
    const onStart = vi.fn().mockRejectedValue(new Error("409: busy"));
    render(<LevelPanel levels={[level]} attempt={null} onStart={onStart} onHint={vi.fn()} onSubmit={vi.fn()} busy={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Start level" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("409: busy");
  });
});
