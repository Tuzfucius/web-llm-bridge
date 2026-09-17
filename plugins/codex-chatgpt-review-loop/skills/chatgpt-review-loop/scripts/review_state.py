"""Persistent, repository-scoped state for the review loop."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

class StateError(RuntimeError):
    code = "STATE_CORRUPT"


def state_path(repo_root: str | os.PathLike[str]) -> Path:
    """Return the state file below *repo_root* (never the process cwd)."""
    import subprocess
    root = Path(repo_root).resolve()
    result = subprocess.run(["git", "rev-parse", "--git-path", "codex-chatgpt-review/state.json"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    path = Path(result)
    return path if path.is_absolute() else root / path


def default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "session_id": None,
        "conversation_url": None,
        "round": 0,
        "last_review_sha": None,
        "passed_sha": None,
        "pending_request_id": None,
        "last_status": None,
        # Hash of the original task, used only to distinguish a new task after
        # MAX_ROUNDS without persisting the full review context.
        "cycle_id": None,
    }


def load_state(repo_root: str | os.PathLike[str]) -> dict[str, Any]:
    path = state_path(repo_root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default_state()
    except (OSError, json.JSONDecodeError) as error:
        raise StateError(f"invalid review state: {error}") from error
    if not isinstance(value, dict):
        raise StateError("review state must be a JSON object")
    result = default_state()
    result.update(value)
    return result


def save_state(repo_root: str | os.PathLike[str], state: Mapping[str, Any]) -> Path:
    """Atomically save JSON state, creating the repository-local directory."""
    path = state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dict(state), ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return path
