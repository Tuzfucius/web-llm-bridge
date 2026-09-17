"""Persistent, repository-scoped state for the review loop."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


STATE_VERSION = 2


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
        "version": STATE_VERSION,
        "session_id": None,
        "conversation_url": None,
        "round": 0,
        "last_review_sha": None,
        "passed_sha": None,
        "pending_request_id": None,
        "last_status": None,
        # The task hash guards an active cycle against Original task drift.
        "task_hash": None,
        # The cycle identity isolates request IDs across independent reviews.
        "cycle_id": None,
    }


def _has_active_cycle(state: Mapping[str, Any]) -> bool:
    return state.get("last_status") == "REVISE" or bool(state.get("pending_request_id"))


def _migrate(value: Mapping[str, Any]) -> dict[str, Any]:
    result = default_state()
    result.update(value)
    version = value.get("version", 1)
    if version == 1:
        # Version 1 stored the task hash in cycle_id. Preserve that value for
        # an active request so recovery remains at-most-once; inactive state
        # starts a fresh cycle on the next driver invocation.
        legacy_id = value.get("cycle_id")
        if isinstance(legacy_id, str) and legacy_id:
            result["task_hash"] = legacy_id
            result["cycle_id"] = legacy_id if _has_active_cycle(value) else None
        else:
            result["task_hash"] = None
            result["cycle_id"] = None
        result["version"] = STATE_VERSION
    elif version != STATE_VERSION:
        result["version"] = STATE_VERSION
    return result


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
    return _migrate(value)


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
