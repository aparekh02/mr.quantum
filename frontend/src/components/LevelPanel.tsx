import { useEffect, useState } from "react";
import type { AttemptInfo, LevelInfo } from "../api/types";

interface Props {
  levels: LevelInfo[];
  attempt: AttemptInfo | null;
  onStart: (levelId: string) => Promise<void>;
  onHint: () => Promise<string | null>;
  onSubmit: () => Promise<void>;
  busy: boolean;
}

export function LevelPanel({ levels, attempt, onStart, onHint, onSubmit, busy }: Props) {
  const [hints, setHints] = useState<string[]>([]);
  const [exhausted, setExhausted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New attempt, fresh hints. Depends only on the attempt's id.
  const attemptId = attempt?.id;
  useEffect(() => {
    setHints([]);
    setExhausted(false);
    setError(null);
  }, [attemptId]);

  async function guard(action: () => Promise<void>): Promise<void> {
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const errorLine = error && (
    <p role="alert" className="error">
      {error}
    </p>
  );

  if (!attempt) {
    return (
      <section className="levels" aria-label="Levels">
        <h2>Levels</h2>
        {levels.map((level) => (
          <article key={level.id} className="level-card">
            <h3>
              {level.order}. {level.title}
            </h3>
            <p className="concept">{level.concept}</p>
            <button type="button" disabled={busy} onClick={() => void guard(() => onStart(level.id))}>
              Start level
            </button>
          </article>
        ))}
        {errorLine}
      </section>
    );
  }

  const level = levels.find((l) => l.id === attempt.level_id);
  const result = attempt.evaluation;
  const allHints = exhausted || (level !== undefined && hints.length >= level.hint_count);

  return (
    <section className="levels" aria-label="Level">
      <h2>
        {level ? `${level.order}. ${level.title}` : attempt.level_id}
      </h2>
      {level && <p className="concept">{level.concept}</p>}
      {level && <p className="objective">{level.objective}</p>}
      <p data-testid="measurements" className="measurements">
        {attempt.measurements} / {level?.measurement_budget ?? "?"} measurements
      </p>
      {hints.length > 0 && (
        <ul className="hints">
          {hints.map((h) => (
            <li key={h}>{h}</li>
          ))}
        </ul>
      )}
      {!result && (
        <div className="level-actions">
          <button
            type="button"
            disabled={allHints}
            onClick={() =>
              void guard(async () => {
                const hint = await onHint();
                if (hint === null) setExhausted(true);
                else setHints((list) => [...list, hint]);
              })
            }
          >
            Show a hint
          </button>
          <button type="button" disabled={busy} onClick={() => void guard(onSubmit)}>
            Submit
          </button>
        </div>
      )}
      {result && (
        <div data-testid="result" className={result.success ? "result ok" : "result fail"}>
          <strong>{result.success ? "Level complete" : "Not yet"}</strong> — {result.score} points,{" "}
          {Math.round(result.accuracy * 100)}% accuracy, {result.measurements} measurements
          {result.feedback.map((f) => (
            <p key={f}>{f}</p>
          ))}
          <button type="button" disabled={busy} onClick={() => void guard(() => onStart(attempt.level_id))}>
            Try again
          </button>
        </div>
      )}
      {errorLine}
    </section>
  );
}
