import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { type Client, createClient } from "./api/client";
import { EventStream, type SocketLike, type StreamStatus } from "./api/stream";
import type { DeviceInfo, PadInfo, RoutineInfo, TrainerEvent, Voltages } from "./api/types";
import { CsdPanel } from "./components/CsdPanel";
import { GateSliders } from "./components/GateSliders";
import { Heatmap } from "./components/Heatmap";
import { RunPanel } from "./components/RunPanel";
import { TraceChart } from "./components/TraceChart";
import { MapAccumulator } from "./state/maps";
import { applyEvents, emptyTraces } from "./state/traces";

const DEFAULT_DEVICE = "dqd_with_sensor";

interface Props {
  client?: Client;
  createSocket?: (url: string) => SocketLike;
}

export function App({ client = defaultClient, createSocket }: Props) {
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [device, setDevice] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pads, setPads] = useState<PadInfo[]>([]);
  const [voltages, setVoltages] = useState<Voltages>({});
  const [routines, setRoutines] = useState<RoutineInfo[]>([]);
  const [traces, dispatch] = useReducer(applyEvents, emptyTraces);
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const maps = useRef(new MapAccumulator());
  const [mapVersion, setMapVersion] = useState(0);
  const frame = useRef(false);

  // 2D points can arrive by the thousand per second: the heatmap re-renders at
  // most once per animation frame. The 1D trace reducer ignores 2D data and so
  // returns the same state for it, which React skips without rendering.
  const scheduleMapRender = useCallback(() => {
    if (frame.current) return;
    frame.current = true;
    const run = () => {
      frame.current = false;
      setMapVersion(maps.current.version);
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
    else setTimeout(run, 16);
  }, []);

  useEffect(() => {
    client
      .devices()
      .then((list) => {
        setDevices(list);
        const preferred = list.find((d) => d.name === DEFAULT_DEVICE) ?? list[0];
        if (preferred) setDevice(preferred.name);
      })
      .catch((e: unknown) => setError(String(e instanceof Error ? e.message : e)));
  }, [client]);

  useEffect(() => {
    if (!device) return;
    let cancelled = false;
    (async () => {
      const session = await client.createSession(device);
      const [p, v, r] = await Promise.all([
        client.pads(session.id),
        client.voltages(session.id),
        client.routines(session.id),
      ]);
      if (cancelled) return;
      setPads(p);
      setVoltages(v);
      setRoutines(r);
      setSessionId(session.id);
    })().catch((e: unknown) => setError(String(e instanceof Error ? e.message : e)));
    return () => {
      cancelled = true;
    };
  }, [client, device]);

  const refreshVoltages = useCallback(
    (sid: string) => {
      client
        .voltages(sid)
        .then(setVoltages)
        .catch(() => undefined);
    },
    [client],
  );

  useEffect(() => {
    if (!sessionId) return;
    maps.current = new MapAccumulator();
    const onEvent = (event: TrainerEvent) => {
      dispatch([event]);
      const before = maps.current.version;
      maps.current.apply(event);
      if (maps.current.version !== before) scheduleMapRender();
      if (event.kind === "run_started") {
        setRunning(true);
        setLastRun(`${event.routine} running…`);
      } else if (event.kind === "run_finished") {
        setRunning(false);
        setLastRun(`${event.routine} succeeded`);
        refreshVoltages(sessionId);
      } else if (event.kind === "run_failed") {
        const data = (event.data ?? {}) as { error?: string };
        setRunning(false);
        setLastRun(`${event.routine} failed: ${data.error ?? "unknown error"}`);
        refreshVoltages(sessionId);
      }
    };
    const stream = new EventStream({
      url: (after) => client.streamUrl(sessionId, after),
      onEvent,
      onStatus: setStatus,
      ...(createSocket ? { createSocket } : {}),
    });
    stream.start();
    return () => stream.stop();
  }, [client, sessionId, createSocket, refreshVoltages, scheduleMapRender]);

  const onSet = useCallback(
    (v: Voltages) => {
      if (!sessionId) return Promise.reject(new Error("no session"));
      return client.setVoltages(sessionId, v);
    },
    [client, sessionId],
  );

  const onRun = useCallback(
    async (routine: string, parameters: Record<string, unknown>) => {
      if (!sessionId) throw new Error("no session");
      await client.startRun(sessionId, routine, parameters);
    },
    [client, sessionId],
  );

  const onPick = useCallback(
    (v: Voltages) => {
      if (!sessionId) return;
      client
        .setVoltages(sessionId, v)
        .then(setVoltages)
        .catch((e: unknown) => setError(String(e instanceof Error ? e.message : e)));
    },
    [client, sessionId],
  );

  const map = mapVersion >= 0 ? maps.current.latest() : null;

  return (
    <main className="app" data-session-id={sessionId ?? undefined}>
      <header>
        <h1>Tune-Up Trainer</h1>
        <label>
          Device
          <select
            aria-label="Device"
            value={device ?? ""}
            onChange={(e) => {
              setSessionId(null);
              setDevice(e.target.value);
            }}
          >
            {devices.map((d) => (
              <option key={d.name} value={d.name}>
                {d.title}
              </option>
            ))}
          </select>
        </label>
        <span data-testid="stream-status" className={`stream stream-${status}`}>
          stream: {status}
        </span>
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="layout">
        <GateSliders pads={pads} voltages={voltages} onSet={onSet} disabled={running} />
        <div className="right">
          <TraceChart trace={traces.latest} />
          {routines.length > 0 && (
            <RunPanel key={sessionId ?? ""} routines={routines} onRun={onRun} running={running} />
          )}
          {lastRun && <p className="last-run">{lastRun}</p>}
        </div>
      </div>
      <section className="two-d" aria-label="Charge stability diagram">
        <Heatmap map={map} onPick={onPick} />
        {pads.length > 0 && (
          <CsdPanel key={sessionId ?? ""} pads={pads} voltages={voltages} onRun={onRun} running={running} />
        )}
      </section>
    </main>
  );
}

const defaultClient = createClient();
