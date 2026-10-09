import { describe, expect, it, vi } from "vitest";
import type { TrainerEvent } from "./types";
import { EventStream, type SocketLike, type StreamStatus } from "./stream";

class FakeSocket implements SocketLike {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  open(): void {
    this.onopen?.();
  }
  send(event: Partial<TrainerEvent> & { seq: number }): void {
    this.onmessage?.({
      data: JSON.stringify({ time: 0, kind: "measurement", routine: "r", name: "n", data: {}, ...event }),
    });
  }
  drop(): void {
    this.onclose?.();
  }
  close(): void {
    this.closed = true;
  }
}

function setup(backoff = [10, 20]) {
  FakeSocket.instances = [];
  const received: number[] = [];
  const statuses: StreamStatus[] = [];
  const timers: Array<() => void> = [];
  const stream = new EventStream({
    url: (after) => `ws://x/stream?after=${after}`,
    createSocket: (url) => new FakeSocket(url),
    onEvent: (e) => received.push(e.seq),
    onStatus: (s) => statuses.push(s),
    backoffMs: backoff,
    schedule: (fn) => {
      timers.push(fn);
      return () => undefined;
    },
  });
  const socket = (i: number) => {
    const s = FakeSocket.instances[i];
    if (!s) throw new Error(`no socket ${i}`);
    return s;
  };
  return { stream, received, statuses, timers, socket };
}

describe("EventStream", () => {
  it("delivers events in order and tracks the last seq", () => {
    const { stream, received, socket } = setup();
    stream.start();
    socket(0).open();
    socket(0).send({ seq: 1 });
    socket(0).send({ seq: 2 });
    expect(received).toEqual([1, 2]);
    expect(stream.lastSeq).toBe(2);
    expect(socket(0).url).toBe("ws://x/stream?after=0");
  });

  it("reconnects after a drop and resumes from the last seq", () => {
    const { stream, received, statuses, timers, socket } = setup();
    stream.start();
    socket(0).open();
    socket(0).send({ seq: 1 });
    socket(0).send({ seq: 2 });
    socket(0).drop();
    expect(statuses.at(-1)).toBe("reconnecting");
    timers.shift()?.();
    expect(socket(1).url).toBe("ws://x/stream?after=2");
    socket(1).open();
    socket(1).send({ seq: 3 });
    expect(received).toEqual([1, 2, 3]);
    expect(statuses.at(-1)).toBe("open");
  });

  it("ignores duplicates replayed after a reconnect", () => {
    const { stream, received, timers, socket } = setup();
    stream.start();
    socket(0).open();
    socket(0).send({ seq: 1 });
    socket(0).drop();
    timers.shift()?.();
    socket(1).open();
    socket(1).send({ seq: 1 });
    socket(1).send({ seq: 2 });
    expect(received).toEqual([1, 2]);
  });

  it("never skips: a gap forces a reconnect from the last seq", () => {
    const { stream, received, timers, socket } = setup();
    stream.start();
    socket(0).open();
    socket(0).send({ seq: 1 });
    socket(0).send({ seq: 3 });
    expect(received).toEqual([1]);
    expect(socket(0).closed).toBe(true);
    timers.shift()?.();
    expect(socket(1).url).toBe("ws://x/stream?after=1");
  });

  it("backs off between attempts, capped at the last delay", () => {
    const delays: number[] = [];
    FakeSocket.instances = [];
    const stream = new EventStream({
      url: (after) => `ws://x?after=${after}`,
      createSocket: (url) => new FakeSocket(url),
      onEvent: () => undefined,
      backoffMs: [10, 20],
      schedule: (fn, ms) => {
        delays.push(ms);
        fn();
        return () => undefined;
      },
    });
    stream.start();
    for (let i = 0; i < 3; i++) FakeSocket.instances.at(-1)?.drop();
    expect(delays).toEqual([10, 20, 20]);
  });

  it("stop() closes the socket and does not reconnect", () => {
    const { stream, timers, socket, statuses } = setup();
    stream.start();
    socket(0).open();
    stream.stop();
    expect(socket(0).closed).toBe(true);
    socket(0).drop();
    expect(timers).toHaveLength(0);
    expect(statuses.at(-1)).toBe("closed");
  });

  it("can start from a known cursor", () => {
    const { stream, socket } = setup();
    stream.start(41);
    expect(socket(0).url).toBe("ws://x/stream?after=41");
  });

  it("reports malformed messages without breaking the stream", () => {
    const onError = vi.fn();
    FakeSocket.instances = [];
    const got: number[] = [];
    const stream = new EventStream({
      url: () => "ws://x",
      createSocket: (url) => new FakeSocket(url),
      onEvent: (e) => got.push(e.seq),
      onError,
      schedule: () => () => undefined,
    });
    stream.start();
    const s = FakeSocket.instances[0];
    s?.onmessage?.({ data: "not json" });
    s?.send({ seq: 1 });
    expect(onError).toHaveBeenCalledOnce();
    expect(got).toEqual([1]);
  });
});
