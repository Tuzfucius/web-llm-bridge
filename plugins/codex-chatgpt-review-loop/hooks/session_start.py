"""Prepare bounded review-loop context for a Codex SessionStart hook."""

from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        payload = {}

    # Keep transport and state in the bridge; this hook only supplies lifecycle
    # policy.  The continuation keeps the context block available to the Skill.
    workspace = payload.get("cwd") or "the current workspace"
    context = f"""Codex ChatGPT Review Loop lifecycle policy (workspace: {workspace})

Use only the repository Web LLM Bridge path through the chatgpt-review-loop
Skill. Do not use a private ChatGPT API, cookies, CDP, browser debugging port,
or hook-local state.

For a task where the user explicitly requested code changes, emit
@@REVIEW_READY@@ only at the very end of the development turn and only when all
of these are true: implementation is complete; required tests have run and
passed; there is no blocker or pending user decision; the worktree is clean;
the changes are committed; and, when this workflow requires pushing, the
commit is pushed to its upstream. Immediately before the marker, include this
deterministic context block, using the real task and results:

@@REVIEW_CONTEXT_BEGIN@@
Original task:
<the user's original development goal>

Implementation summary:
<what this turn actually changed>

Tests:
<tests actually run and their results>
@@REVIEW_CONTEXT_END@@

Do not emit @@REVIEW_READY@@ for questions, explanations, architecture
analysis, read-only work, unrequested changes, incomplete implementation,
failed tests, a dirty or uncommitted worktree, a blocker, a pending user
choice, or work already passed by external review. The Skill must preserve the
original task in later review cycles while updating the summary and tests.

When the Skill reports PASS, finish with @@WEB_REVIEW_PASS@@ and do not emit
@@REVIEW_READY@@. When it reports REVISE, follow its concrete prompt, test,
commit/push as applicable, produce a new context block, and then emit
@@REVIEW_READY@@. The Stop hook only decides whether to continue; it never
communicates with the browser or Bridge.
"""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
