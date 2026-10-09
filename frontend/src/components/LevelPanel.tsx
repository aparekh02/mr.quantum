import { useEffect, useState } from "react";
import type { AttemptInfo, LevelInfo, LevelProgress } from "../api/types";

interface Props {
  levels: LevelInfo[];
  /** Per-player progress; absent in free play (everything open). */
  progress?: LevelProgress[] | null;
  attempt: AttemptInfo | null;
  onStart: (levelId: string) => Promise<void>;
  onHint: () => Promise<string | null>;
  onSubmit: () => Promise<void>;
  /** Leave a finished attempt and go back to the level picker. */
  onLeave?: () => void;
  busy: boolean;
}

export function LevelPanel({
  levels,
  progress = null,
  attempt,
  onStart,
  onHint,
  onSubmit,
  onLeave,
  busy,
}: Props) {
  const [hints, setHints] = useState<string[]>([]);
  const [exhausted, setExhausted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

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

  const status = (id: string) => progress?.find((p) => p.id === id);
  const open = (id: string) => status(id)?.unlocked ?? true;
  const label = (level: LevelInfo) => {
    const s = status(level.id);
    const base = `Level ${level.order} — ${level.title}`;
    if (s?.completed) return `✓ ${base} (best ${s.best_score})`;
    if (s && !s.unlocked) return `🔒 ${base}`;
    return base;
  };

  if (!attempt) {
    const next = levels.find((l) => open(l.id) && !status(l.id)?.completed);
    const fallback = progress ? (next ?? levels.find((l) => open(l.id))) : levels[0];
    const picked = levels.find((l) => l.id === selected && open(l.id));
    const chosen = picked ?? fallback ?? levels[0];
    return (
      <section className="levels" aria-label="Levels">
        <h2>Levels</h2>
        {levels.length > 1 && (
          <label>
            Level{" "}
            <select aria-label="Level" value={chosen?.id ?? ""} onChange={(e) => setSelected(e.target.value)}>
              {levels.map((level) => (
                <option key={level.id} value={level.id} disabled={!open(level.id)}>
                  {label(level)}
                </option>
              ))}
            </select>
          </label>
        )}
        {chosen && (
          <article className="level-card">
            <h3>
              {chosen.order}. {chosen.title}
            </h3>
            <p className="concept">{chosen.concept}</p>
            <button
              type="button"
              disabled={busy || !open(chosen.id)}
              onClick={() => void guard(() => onStart(chosen.id))}
            >
              Start level
            </button>
          </article>
        )}
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
      {!result && <p className="hint-cost">Each hint costs 10% of your score.</p>}
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
          {attempt.explanation && attempt.explanation.length > 0 && (
            <div data-testid="explanation" className="explanation">
              <h3>Why it works</h3>
              {attempt.explanation.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </div>
          )}
          <button type="button" disabled={busy} onClick={() => void guard(() => onStart(attempt.level_id))}>
            Try again
          </button>
          {onLeave && (
            <button type="button" disabled={busy} onClick={onLeave}>
              Choose another level
            </button>
          )}
        </div>
      )}
      {errorLine}
    </section>
  );
}
