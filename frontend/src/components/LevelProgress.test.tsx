import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AttemptInfo, LevelInfo, LevelProgress } from "../api/types";
import { LevelPanel } from "./LevelPanel";

const make = (order: number, id: string, title: string): LevelInfo => ({
  id, order, title, concept: `Concept ${order}.`, objective: `Objective ${order}.`,
  device: "dqd_with_sensor", hint_count: 1, measurement_budget: 1000,
});
const levels = [make(1, "coulomb-peak", "One"), make(2, "compensate-sensor", "Two"), make(3, "double-dot", "Three")];
const progress = (done: number): LevelProgress[] =>
  levels.map((l, k) => ({
    id: l.id, order: l.order, unlocked: k <= done, completed: k < done,
    attempts: k < done ? 2 : 0, best_score: k < done ? 800 + k : 0, best_accuracy: 0.9, hints_used: 0,
  }));

describe("LevelPanel with progress", () => {
  it("marks completed and locked levels and disables locked ones", () => {
    render(
      <LevelPanel levels={levels} progress={progress(1)} attempt={null} onStart={vi.fn()} onHint={vi.fn()} onSubmit={vi.fn()} busy={false} />,
    );
    const options = Array.from((screen.getByLabelText("Level") as HTMLSelectElement).options);
    expect(options.map((o) => o.text)).toEqual([
      "✓ Level 1 — One (best 800)",
      "Level 2 — Two",
      "🔒 Level 3 — Three",
    ]);
    expect(options[2]?.disabled).toBe(true);
  });

  it("defaults to the first level not yet completed", () => {
    render(
      <LevelPanel levels={levels} progress={progress(1)} attempt={null} onStart={vi.fn()} onHint={vi.fn()} onSubmit={vi.fn()} busy={false} />,
    );
    expect(screen.getByText("2. Two")).toBeInTheDocument();
  });

  it("cannot start a locked level", async () => {
    const onStart = vi.fn();
    render(
      <LevelPanel levels={levels} progress={progress(0)} attempt={null} onStart={onStart} onHint={vi.fn()} onSubmit={vi.fn()} busy={false} />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Level"), "double-dot").catch(() => undefined);
    await userEvent.click(screen.getByRole("button", { name: "Start level" }));
    expect(onStart).toHaveBeenCalledWith("coulomb-peak"); // locked option could not be chosen
  });

  it("explains the physics after submitting", () => {
    const attempt: AttemptInfo = {
      id: "a", level_id: "coulomb-peak", session_id: "s", status: "submitted", measurements: 5, hints_shown: 0,
      evaluation: { success: true, accuracy: 0.9, score: 900, measurements: 5, feedback: ["ok"] },
      explanation: ["Adding a charge costs energy.", "Peaks are evenly spaced."],
    };
    render(<LevelPanel levels={levels} attempt={attempt} onStart={vi.fn()} onHint={vi.fn()} onSubmit={vi.fn()} busy={false} />);
    const why = screen.getByTestId("explanation");
    expect(why).toHaveTextContent("Why it works");
    expect(why).toHaveTextContent("Adding a charge costs energy.");
    expect(why).toHaveTextContent("Peaks are evenly spaced.");
  });

  it("notes that hints cost points", () => {
    const attempt: AttemptInfo = {
      id: "a", level_id: "coulomb-peak", session_id: "s", status: "active", measurements: 0, hints_shown: 0, evaluation: null,
    };
    render(<LevelPanel levels={levels} attempt={attempt} onStart={vi.fn()} onHint={vi.fn()} onSubmit={vi.fn()} busy={false} />);
    expect(screen.getByText(/each hint costs 10%/i)).toBeInTheDocument();
  });

  it("can leave a finished attempt to pick another level", async () => {
    const onLeave = vi.fn();
    const attempt: AttemptInfo = {
      id: "a", level_id: "coulomb-peak", session_id: "s", status: "submitted", measurements: 5, hints_shown: 0,
      evaluation: { success: true, accuracy: 0.9, score: 900, measurements: 5, feedback: ["ok"] },
    };
    render(<LevelPanel levels={levels} attempt={attempt} onStart={vi.fn()} onHint={vi.fn()} onSubmit={vi.fn()} onLeave={onLeave} busy={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Choose another level" }));
    expect(onLeave).toHaveBeenCalledOnce();
  });
});
