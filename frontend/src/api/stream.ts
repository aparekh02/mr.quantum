import type { TrainerEvent } from "./types";

// A websocket reader that never loses or repeats an event. Every event carries a
// contiguous seq; the stream remembers the last one delivered, drops duplicates,
// and on a drop or a gap reconnects asking the server for events after it.

export type StreamStatus = "connecting" | "open" | "reconnecting" | "closed";

export interface SocketLike {
  onopen: (() => void) | null;
  onmessage: ((e: { data: string }) => void) | null;
  onclose: (() => void) | null;
  close(): void;
}

export interface StreamOptions {
  url: (after: number) => string;
  onEvent: (event: TrainerEvent) => void;
  onStatus?: (status: StreamStatus) => void;
  onError?: (error: unknown) => void;
  createSocket?: (url: string) => SocketLike;
  backoffMs?: number[];
  schedule?: (fn: () => void, ms: number) => () => void;
}

const defaultSchedule = (fn: () => void, ms: number) => {
  const id = setTimeout(fn, ms);
  return () => clearTimeout(id);
};

export class EventStream {
  lastSeq = 0;
  private socket: SocketLike | null = null;
  private attempt = 0;
  private stopped = true;
  private cancelRetry: (() => void) | null = null;

  constructor(private opts: StreamOptions) {}

  start(after = 0): void {
    this.lastSeq = after;
    this.stopped = false;
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    this.cancelRetry?.();
    this.socket?.close();
    this.socket = null;
    this.opts.onStatus?.("closed");
  }

  private connect(): void {
    this.opts.onStatus?.(this.attempt === 0 ? "connecting" : "reconnecting");
    const create = this.opts.createSocket ?? browserSocket;
    const socket = create(this.opts.url(this.lastSeq));
    this.socket = socket;
    socket.onopen = () => {
      this.attempt = 0;
      this.opts.onStatus?.("open");
    };
    socket.onmessage = (message) => this.receive(socket, message.data);
    socket.onclose = () => {
      if (this.socket === socket) this.retry();
    };
  }

  private receive(socket: SocketLike, raw: string): void {
    let event: TrainerEvent;
    try {
      event = JSON.parse(raw) as TrainerEvent;
    } catch (error) {
      this.opts.onError?.(error);
      return;
    }
    if (event.seq <= this.lastSeq) return; // replayed duplicate
    if (event.seq !== this.lastSeq + 1) {
      // A gap: something was missed. Resume from the last event we have.
      this.socket = null;
      socket.close();
      this.retry();
      return;
    }
    this.lastSeq = event.seq;
    this.opts.onEvent(event);
  }

  private retry(): void {
    if (this.stopped) return;
    const delays = this.opts.backoffMs ?? [250, 500, 1000, 2000, 4000];
    const delay = delays[Math.min(this.attempt, delays.length - 1)] ?? 1000;
    this.attempt += 1;
    this.opts.onStatus?.("reconnecting");
    const schedule = this.opts.schedule ?? defaultSchedule;
    this.cancelRetry = schedule(() => {
      if (!this.stopped) this.connect();
    }, delay);
  }
}

function browserSocket(url: string): SocketLike {
  const ws = new WebSocket(url);
  const adapter: SocketLike = {
    onopen: null,
    onmessage: null,
    onclose: null,
    close: () => ws.close(),
  };
  ws.onopen = () => adapter.onopen?.();
  ws.onmessage = (e: MessageEvent) => adapter.onmessage?.({ data: String(e.data) });
  ws.onclose = () => adapter.onclose?.();
  return adapter;
}
