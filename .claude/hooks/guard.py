"""PreToolUse guard enforcing CLAUDE.md rules on file-editing tools.

- Editing an upstream file (or adding one under stanza/) asks the user first.
- Modifying an existing file in tests/regression/ is denied (append-only).
- Adding a type-ignore comment or a pytest/unittest skip or xfail to a .py
  file is denied.

Reads the hook payload as JSON on stdin; prints a decision as JSON on stdout,
or nothing when it has no opinion. Standard library only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_REF = "upstream/main"

# New files we are allowed to add inside upstream's package (CLAUDE.md).
ALLOWED_NEW_UPSTREAM_PATHS = frozenset({"stanza/drivers/simulator.py"})
REGRESSION_DIR = "tests/regression/"

# Used only when git cannot list the upstream tree.
FALLBACK_UPSTREAM_PREFIXES = ("stanza/", "tests/", "docs/", "cookbooks/", "scripts/")
FALLBACK_OWNED_PREFIXES = ("tests/harness/", "tests/regression/")

ESCAPE_HATCHES = (
    ("type-ignore comment", re.compile(r"#\s*type\s*:\s*ignore")),
    ("pytest skip/xfail mark", re.compile(r"pytest\.mark\.(skip|skipif|xfail)\b")),
    ("pytest skip/xfail call", re.compile(r"pytest\.(skip|xfail)\s*\(")),
    (
        "unittest skip",
        re.compile(r"unittest\.(skip|skipIf|skipUnless|expectedFailure)\b"),
    ),
)


@dataclass(frozen=True)
class Decision:
    permission: str  # "ask" | "deny"
    reason: str


def upstream_files(root: Path) -> frozenset[str]:
    """Repo-relative paths that belong to upstream Stanza."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-r", "--name-only", UPSTREAM_REF],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return frozenset(line for line in out.splitlines() if line)
    except (OSError, subprocess.CalledProcessError):
        found = set()
        for path in root.rglob("*"):
            rel = path.relative_to(root).as_posix()
            if (
                path.is_file()
                and rel.startswith(FALLBACK_UPSTREAM_PREFIXES)
                and not rel.startswith(FALLBACK_OWNED_PREFIXES)
            ):
                found.add(rel)
        return frozenset(found)


def _old_and_new_text(
    tool_name: str, tool_input: dict[str, Any], current_text: str | None
) -> tuple[str, str]:
    if tool_name == "Write":
        return current_text or "", str(tool_input.get("content", ""))
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        old = "\n".join(str(e.get("old_string", "")) for e in edits)
        new = "\n".join(str(e.get("new_string", "")) for e in edits)
        return old, new
    return str(tool_input.get("old_string", "")), str(tool_input.get("new_string", ""))


def decide(
    rel_path: str,
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    current_text: str | None,
    upstream_files: frozenset[str],
) -> Decision | None:
    """Return a decision for one file edit, or None to leave it to the user."""
    exists = current_text is not None or rel_path in upstream_files
    if rel_path.startswith(REGRESSION_DIR) and (exists or tool_name != "Write"):
        return Decision(
            "deny",
            f"{rel_path} is in tests/regression/, which is append-only. "
            "Add a new file instead; changing an existing one needs the user.",
        )

    if rel_path.endswith((".py", ".pyi")):
        old, new = _old_and_new_text(tool_name, tool_input, current_text)
        for label, pattern in ESCAPE_HATCHES:
            if len(pattern.findall(new)) > len(pattern.findall(old)):
                return Decision(
                    "deny",
                    f"Adding a {label} is forbidden by CLAUDE.md. "
                    "If you are stuck, say so and stop.",
                )

    is_upstream = rel_path in upstream_files or (
        rel_path.startswith("stanza/") and rel_path not in ALLOWED_NEW_UPSTREAM_PATHS
    )
    if is_upstream:
        return Decision(
            "ask",
            f"{rel_path} is an upstream Stanza file. CLAUDE.md: stop and tell the "
            "user before touching upstream, so we stay rebaseable.",
        )
    return None


def main() -> int:
    payload = json.load(sys.stdin)
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input", {}) or {}
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw_path:
        return 0

    path = Path(raw_path).resolve()
    try:
        rel_path = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return 0

    current_text = path.read_text(errors="replace") if path.is_file() else None
    decision = decide(
        rel_path,
        tool_name,
        tool_input,
        current_text=current_text,
        upstream_files=upstream_files(REPO_ROOT),
    )
    if decision is not None:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision.permission,
                "permissionDecisionReason": decision.reason,
            }
        }
        print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
