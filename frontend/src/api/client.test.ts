import { describe, expect, it, vi } from "vitest";
import { ApiError, createClient } from "./client";

function respond(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

describe("API client", () => {
  it("calls the documented endpoints under the base path", async () => {
    const fetchImpl = respond(201, { id: "s1", device: "d", title: "t", groups: {} });
    const client = createClient("/api", fetchImpl);
    await client.createSession("d");
    expect(fetchImpl).toHaveBeenCalledWith("/api/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ device: "d" }),
    });
  });

  it("starts runs and can wait", async () => {
    const fetchImpl = respond(200, { id: "r1", status: "succeeded" });
    await createClient("/api", fetchImpl).startRun("s1", "x", { a: 1 }, true);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/api/sessions/s1/runs?wait=true");
  });

  it("turns error responses into ApiError with the detail", async () => {
    const fetchImpl = respond(422, { detail: [{ msg: "unknown pad NOPE" }] });
    const err = await createClient("/api", fetchImpl)
      .setVoltages("s1", { NOPE: 0 })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(422);
    expect((err as ApiError).message).toContain("unknown pad NOPE");
  });

  it("formats string details too", async () => {
    const err = await createClient("/api", respond(409, { detail: "a routine is running" }))
      .measure("s1", ["PB"])
      .catch((e: unknown) => e);
    expect((err as Error).message).toBe("409: a routine is running");
  });

  it("builds the websocket URL from the page location", () => {
    const client = createClient("/api", respond(200, {}));
    expect(client.streamUrl("s1", 7, { protocol: "https:", host: "lab.example" })).toBe(
      "wss://lab.example/api/sessions/s1/stream?after=7",
    );
  });
});
