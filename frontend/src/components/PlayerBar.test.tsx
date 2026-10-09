import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { isValidPlayer, PlayerBar } from "./PlayerBar";

describe("PlayerBar", () => {
  it("starts in free play and lets a student play as a name", async () => {
    const onChange = vi.fn();
    render(<PlayerBar player={null} onChange={onChange} />);
    expect(screen.getByText(/free play/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "ada_l" } });
    await userEvent.click(screen.getByRole("button", { name: "Save my progress" }));
    expect(onChange).toHaveBeenCalledWith("ada_l");
  });

  it("rejects names the server would refuse", async () => {
    const onChange = vi.fn();
    render(<PlayerBar player={null} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Ada Lovelace!" } });
    await userEvent.click(screen.getByRole("button", { name: "Save my progress" }));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("letters, digits");
  });

  it("shows who is playing and can switch back to free play", async () => {
    const onChange = vi.fn();
    render(<PlayerBar player="ada_l" onChange={onChange} />);
    expect(screen.getByText(/playing as/i)).toHaveTextContent("ada_l");
    await userEvent.click(screen.getByRole("button", { name: "Switch to free play" }));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("validates like the server", () => {
    expect(isValidPlayer("ada")).toBe(true);
    expect(isValidPlayer("a".repeat(64))).toBe(true);
    expect(isValidPlayer("a".repeat(65))).toBe(false);
    expect(isValidPlayer("é")).toBe(false);
    expect(isValidPlayer("")).toBe(false);
  });
});
