import { type FormEvent, useState } from "react";
import type { RoutineInfo } from "../api/types";

interface Props {
  routines: RoutineInfo[];
  onRun: (routine: string, parameters: Record<string, unknown>) => Promise<void>;
  running: boolean;
}

export function templateFor(routine: RoutineInfo): string {
  const required = routine.parameters.filter((p) => p.required).map((p) => [p.name, null]);
  return JSON.stringify(Object.fromEntries(required), null, 2);
}

export function RunPanel({ routines, onRun, running }: Props) {
  const first = routines[0];
  const [selected, setSelected] = useState(first?.name ?? "");
  const [text, setText] = useState(first ? templateFor(first) : "{}");
  const [error, setError] = useState<string | null>(null);

  function choose(name: string): void {
    setSelected(name);
    const routine = routines.find((r) => r.name === name);
    if (routine) setText(templateFor(routine));
    setError(null);
  }

  async function submit(e: FormEvent): Promise<void> {
    e.preventDefault();
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setError("Parameters are not valid JSON");
      return;
    }
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      setError("Parameters must be a JSON object");
      return;
    }
    setError(null);
    try {
      await onRun(selected, parsed as Record<string, unknown>);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <form className="run-panel" onSubmit={(e) => void submit(e)}>
      <label>
        Routine
        <select aria-label="Routine" value={selected} onChange={(e) => choose(e.target.value)}>
          {routines.map((r) => (
            <option key={r.name} value={r.name}>
              {r.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Parameters (JSON)
        <textarea
          aria-label="Parameters (JSON)"
          rows={8}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button type="submit" disabled={running || !selected}>
        {running ? "Running…" : "Run routine"}
      </button>
    </form>
  );
}
