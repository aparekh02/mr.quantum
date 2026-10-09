import { useCallback, useEffect, useReducer, useState } from "react";
import { type Client, createClient } from "./api/client";
import { EventStream, type SocketLike, type StreamStatus } from "./api/stream";
import type { DeviceInfo, PadInfo, RoutineInfo, TrainerEvent, Voltages } from "./api/types";
import { GateSliders } from "./components/GateSliders";
import { RunPanel } from "./components/RunPanel";
import { TraceChart } from "./components/TraceChart";
import { applyEvent, emptyTraces } from "./state/traces";

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
  const [traces, dispatch] = useReducer(applyEvent, emptyTraces);
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    const onEvent = (event: TrainerEvent) => {
      dispatch(event);
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
  }, [client, sessionId, createSocket, refreshVoltages]);

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

  return (
    <main className="app">
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
    </main>
  );
}

const defaultClient = createClient();
