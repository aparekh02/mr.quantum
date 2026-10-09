import { type FormEvent, useState } from "react";

const PLAYER = /^[A-Za-z0-9_-]{1,64}$/;

/** Same rule as the server (trainer.game.progress.validate_player). */
export function isValidPlayer(name: string): boolean {
  return PLAYER.test(name);
}

interface Props {
  player: string | null;
  onChange: (player: string | null) => void;
}

export function PlayerBar({ player, onChange }: Props) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (player) {
    return (
      <div className="player-bar">
        <span>
          Playing as <strong>{player}</strong>: progress is saved.
        </span>
        <button type="button" onClick={() => onChange(null)}>
          Switch to free play
        </button>
      </div>
    );
  }

  function submit(e: FormEvent): void {
    e.preventDefault();
    const trimmed = name.trim();
    if (!isValidPlayer(trimmed)) {
      setError("Use 1–64 letters, digits, '_' or '-'.");
      return;
    }
    setError(null);
    onChange(trimmed);
  }

  return (
    <form className="player-bar" onSubmit={submit}>
      <span>Free play: every level is open and nothing is saved.</span>
      <label>
        Your name
        <input aria-label="Your name" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <button type="submit">Save my progress</button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}
