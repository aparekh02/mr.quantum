import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { Client } from "./api/client";
import type { SocketLike } from "./api/stream";
import type { TrainerEvent } from "./api/types";

class FakeSocket implements SocketLike {
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  constructor(public url: string) {}
  emit(event: Omit<TrainerEvent, "time">): void {
    this.onmessage?.({ data: JSON.stringify({ time: 0, ...event }) });
  }
}

function fakeClient(overrides: Partial<Client> = {}): Client {
  return {
    devices: vi.fn().mockResolvedValue([
      { name: "single_channel", title: "Single channel" },
      { name: "dqd_with_sensor", title: "Double dot" },
    ]),
    createSession: vi.fn().mockImplementation(async (device: string) => ({
      id: `s-${device}`,
      device,
      title: device,
      groups: {},
    })),
    pads: vi.fn().mockResolvedValue([
      { name: "PB", pad_type: "GATE", electrode_type: "PLUNGER", v_lower_bound: -2, v_upper_bound: 0.3, controllable: true, measurable: true, group: null },
    ]),
    voltages: vi.fn().mockResolvedValue({ PB: 0 }),
    setVoltages: vi.fn().mockResolvedValue({ PB: 0 }),
    measure: vi.fn(),
    routines: vi.fn().mockResolvedValue([
      { name: "noise_floor_measurement", parameters: [{ name: "measure_electrode", type: "str", required: true, default: null }] },
    ]),
    startRun: vi.fn().mockResolvedValue({ id: "r1", status: "running" }),
    getRun: vi.fn(),
    events: vi.fn(),
    levels: vi.fn().mockResolvedValue([
      { id: "coulomb-peak", order: 1, title: "Find the Coulomb peak", concept: "Coulomb blockade.", objective: "Do it.", device: "dqd_with_sensor", hint_count: 1, measurement_budget: 2500 },
    ]),
    startAttempt: vi.fn().mockResolvedValue({ id: "a1", level_id: "coulomb-peak", session_id: "s-level", status: "active", measurements: 0, hints_shown: 0, evaluation: null }),
    getAttempt: vi.fn().mockResolvedValue({ id: "a1", level_id: "coulomb-peak", session_id: "s-level", status: "active", measurements: 42, hints_shown: 0, evaluation: null }),
    nextHint: vi.fn(),
    submitAttempt: vi.fn().mockResolvedValue({
      id: "a1", level_id: "coulomb-peak", session_id: "s-level", status: "submitted", measurements: 42, hints_shown: 0,
      evaluation: { success: true, accuracy: 0.9, score: 900, measurements: 42, feedback: ["Well done."] },
    }),
    streamUrl: (sid: string, after: number) => `ws://test/${sid}?after=${after}`,
    ...overrides,
  } as unknown as Client;
}

async function mount(client = fakeClient()) {
  const sockets: FakeSocket[] = [];
  render(
    <App
      client={client}
      createSocket={(url) => {
        const s = new FakeSocket(url);
        sockets.push(s);
        return s;
      }}
    />,
  );
  await screen.findByLabelText("PB");
  await waitFor(() => expect(sockets.length).toBeGreaterThan(0));
  const socket = () => {
    const s = sockets.at(-1);
    if (!s) throw new Error("no socket");
    return s;
  };
  return { client, socket, sockets };
}

describe("App", () => {
  it("opens a session on the double-dot device by default", async () => {
    const { client, socket } = await mount();
    expect(client.createSession).toHaveBeenCalledWith("dqd_with_sensor");
    expect(socket().url).toBe("ws://test/s-dqd_with_sensor?after=0");
  });

  it("streams sweep data into the trace", async () => {
    const { socket } = await mount();
    act(() => {
      socket().onopen?.();
      socket().emit({ seq: 1, kind: "run_started", routine: "r", name: "r", data: {} });
      socket().emit({
        seq: 2,
        kind: "sweep",
        routine: "r",
        name: "n gates sweep",
        data: { x_label: "Voltage", y_label: "Current", x_data: [[0], [1], [2]], y_data: [1, 2, 3] },
      });
    });
    expect(screen.getByTestId("trace")).toHaveAttribute("data-points", "3");
    expect(screen.getByTestId("stream-status")).toHaveTextContent("open");
  });

  it("tracks run state and refreshes voltages when a run ends", async () => {
    const client = fakeClient();
    const { socket } = await mount(client);
    act(() => socket().emit({ seq: 1, kind: "run_started", routine: "r", name: "r", data: {} }));
    expect(screen.getByRole("button", { name: "Running…" })).toBeDisabled();
    (client.voltages as ReturnType<typeof vi.fn>).mockResolvedValue({ PB: -1.25 });
    act(() =>
      socket().emit({ seq: 2, kind: "run_failed", routine: "r", name: "r", data: { error: "boom" } }),
    );
    await waitFor(() => expect(screen.getByTestId("value-PB")).toHaveTextContent("-1.250 V"));
    expect(screen.getByText(/r failed: boom/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run routine" })).toBeEnabled();
  });

  it("starts a run through the client", async () => {
    const { client } = await mount();
    await userEvent.click(screen.getByRole("button", { name: "Run routine" }));
    expect(client.startRun).toHaveBeenCalledWith("s-dqd_with_sensor", "noise_floor_measurement", {
      measure_electrode: null,
    });
  });

  it("switching device opens a new session and a new stream", async () => {
    const { client, sockets } = await mount();
    await userEvent.selectOptions(screen.getByLabelText("Device"), "single_channel");
    await waitFor(() => expect(client.createSession).toHaveBeenLastCalledWith("single_channel"));
    await waitFor(() => expect(sockets.at(-1)?.url).toBe("ws://test/s-single_channel?after=0"));
    expect(sockets[0]?.close).toHaveBeenCalled();
  });

  it("shows a startup error", async () => {
    render(<App client={fakeClient({ devices: vi.fn().mockRejectedValue(new Error("API down")) })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("API down");
  });

  it("streams a 2D sweep into the heatmap and a click sets both gates", async () => {
    const client = fakeClient({
      setVoltages: vi.fn().mockResolvedValue({ PB: 0, PA1: -0.6, PA2: -0.6 }),
    });
    const { socket } = await mount(client);
    const x_data: number[][] = [];
    const y_data: number[] = [];
    act(() => {
      let seq = 0;
      for (let j = 0; j < 3; j++) {
        for (let i = 0; i < 3; i++) {
          seq += 1;
          const x = [-0.7 + 0.1 * j, -0.7 + 0.1 * i];
          x_data.push(x);
          y_data.push(seq);
          socket().emit({ seq, kind: "sweep_point", routine: "charge_stability_diagram", name: "PA2 and PA1 sweep", data: { x, y: [seq] } });
        }
      }
      socket().emit({
        seq: 10, kind: "sweep", routine: "charge_stability_diagram", name: "PA2 and PA1 sweep",
        data: { x_label: ["PA2", "PA1"], y_label: "Current", x_data, y_data },
      });
    });
    const heatmap = await screen.findByTestId("heatmap");
    expect(heatmap).toHaveAttribute("data-cells", "9");
    vi.spyOn(heatmap, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 0, left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, toJSON: () => ({}),
    } as DOMRect);
    fireEvent.click(heatmap, { clientX: 0, clientY: 100 });
    await waitFor(() =>
      expect(client.setVoltages).toHaveBeenCalledWith("s-dqd_with_sensor", { PA1: -0.7, PA2: -0.7 }),
    );
  });

  it("exposes the session id for scripted checks", async () => {
    await mount();
    expect(document.querySelector("[data-session-id]")?.getAttribute("data-session-id")).toBe(
      "s-dqd_with_sensor",
    );
  });

  it("starting a level switches to the attempt's session and stream", async () => {
    const { client, sockets } = await mount();
    await userEvent.click(await screen.findByRole("button", { name: "Start level" }));
    await waitFor(() => expect(sockets.at(-1)?.url).toBe("ws://test/s-level?after=0"));
    expect(client.startAttempt).toHaveBeenCalledWith("coulomb-peak");
    expect(client.pads).toHaveBeenLastCalledWith("s-level");
    expect(screen.getByText("Do it.")).toBeInTheDocument();
  });

  it("refreshes the measurement count when a run finishes, and submits", async () => {
    const { client, socket } = await mount();
    await userEvent.click(await screen.findByRole("button", { name: "Start level" }));
    await waitFor(() => expect(socket().url).toBe("ws://test/s-level?after=0"));
    act(() => socket().emit({ seq: 1, kind: "run_finished", routine: "r", name: "r", data: {} }));
    await waitFor(() => expect(screen.getByTestId("measurements")).toHaveTextContent("42 / 2500"));
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(client.submitAttempt).toHaveBeenCalledWith("a1");
    expect(await screen.findByTestId("result")).toHaveTextContent("900 points");
  });

  it("attempt updates never reconnect the stream (no history replay)", async () => {
    const { client, sockets, socket } = await mount();
    await userEvent.click(await screen.findByRole("button", { name: "Start level" }));
    await waitFor(() => expect(socket().url).toBe("ws://test/s-level?after=0"));
    const opened = sockets.length;
    act(() => socket().emit({ seq: 1, kind: "run_finished", routine: "r", name: "r", data: {} }));
    await waitFor(() => expect(client.getAttempt).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    await screen.findByTestId("result");
    expect(sockets.length).toBe(opened);
  });
});
