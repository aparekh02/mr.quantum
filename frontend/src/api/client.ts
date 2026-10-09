import type {
  AttemptInfo,
  DeviceInfo,
  LevelInfo,
  LevelProgress,
  PadInfo,
  RoutineInfo,
  RunInfo,
  SessionInfo,
  TrainerEvent,
  Voltages,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    detail: unknown,
  ) {
    super(`${status}: ${formatDetail(detail)}`);
    this.name = "ApiError";
  }
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : JSON.stringify(d)))
      .join("; ");
  }
  return JSON.stringify(detail);
}

type FetchLike = (
  url: string,
  init?: { method?: string; headers?: Record<string, string>; body?: string },
) => Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>;

export interface Location {
  protocol: string;
  host: string;
}

export function createClient(base = "/api", fetchImpl: FetchLike = fetch) {
  async function call<T>(path: string, method = "GET", body?: unknown): Promise<T> {
    const init: { method: string; headers?: Record<string, string>; body?: string } = { method };
    if (body !== undefined) {
      init.headers = { "content-type": "application/json" };
      init.body = JSON.stringify(body);
    }
    const response = await fetchImpl(`${base}${path}`, method === "GET" ? undefined : init);
    if (response.status === 204) return undefined as T;
    const payload = await response.json();
    if (!response.ok) {
      const detail =
        payload && typeof payload === "object" && "detail" in payload ? payload.detail : payload;
      throw new ApiError(response.status, detail);
    }
    return payload as T;
  }

  return {
    devices: () => call<DeviceInfo[]>("/devices"),
    createSession: (device: string) => call<SessionInfo>("/sessions", "POST", { device }),
    pads: (sid: string) => call<PadInfo[]>(`/sessions/${sid}/pads`),
    voltages: (sid: string) => call<Voltages>(`/sessions/${sid}/voltages`),
    setVoltages: (sid: string, voltages: Voltages) =>
      call<Voltages>(`/sessions/${sid}/voltages`, "PUT", { voltages }),
    measure: (sid: string, pads: string[]) =>
      call<{ currents: Record<string, number> }>(`/sessions/${sid}/measure`, "POST", { pads }),
    routines: (sid: string) => call<RoutineInfo[]>(`/sessions/${sid}/routines`),
    startRun: (sid: string, routine: string, parameters: Record<string, unknown>, wait = false) =>
      call<RunInfo>(`/sessions/${sid}/runs${wait ? "?wait=true" : ""}`, "POST", {
        routine,
        parameters,
      }),
    getRun: (sid: string, id: string) => call<RunInfo>(`/sessions/${sid}/runs/${id}`),
    events: (sid: string, after = 0) =>
      call<TrainerEvent[]>(`/sessions/${sid}/events?after=${after}`),
    levels: () => call<LevelInfo[]>("/levels"),
    startAttempt: (levelId: string, player?: string | null) =>
      call<AttemptInfo>(`/levels/${levelId}/attempts`, "POST", player ? { player } : {}),
    progress: (player: string) => call<LevelProgress[]>(`/players/${encodeURIComponent(player)}/progress`),
    getAttempt: (aid: string) => call<AttemptInfo>(`/attempts/${aid}`),
    nextHint: (aid: string) =>
      call<{ hint: string | null; hints_shown: number }>(`/attempts/${aid}/hints`, "POST", {}),
    submitAttempt: (aid: string) => call<AttemptInfo>(`/attempts/${aid}/submit`, "POST", {}),
    streamUrl: (sid: string, after: number, loc: Location = window.location) =>
      `${loc.protocol === "https:" ? "wss" : "ws"}://${loc.host}${base}/sessions/${sid}/stream?after=${after}`,
  };
}

export type Client = ReturnType<typeof createClient>;
