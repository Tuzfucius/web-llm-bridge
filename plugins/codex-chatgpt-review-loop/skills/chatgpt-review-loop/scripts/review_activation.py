"""Repository-local, one-shot authorization for an external review handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


ACTIVATION_VERSION = 1
_TASK_HASH_RE = re.compile(r"[0-9a-f]{24}")
_TARGET_KINDS = {"conversation_url", "session_id"}


class ActivationError(RuntimeError):
    code = "ACTIVATION_INVALID"


class ActivationMissing(ActivationError):
    code = "ACTIVATION_MISSING"


class ActivationConflict(ActivationError):
    code = "ACTIVATION_CONFLICT"


class UnsupportedActivationVersion(ActivationError):
    code = "UNSUPPORTED_ACTIVATION_VERSION"


def activation_path(repo_root: str | os.PathLike[str]) -> Path:
    """Return the Git-scoped activation location for a repository/worktree."""
    root = Path(repo_root).resolve()
    root_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    root = Path(root_result.stdout.strip()).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", "codex-chatgpt-review/activation.json"],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()
    path = Path(result)
    return path if path.is_absolute() else root / path


def normalize_task(task: str) -> str:
    """Use the same task normalization as the review driver's context hash."""
    return str(task or "").strip()


def task_hash(task: str) -> str:
    normalized = normalize_task(task)
    if not normalized:
        raise ActivationError("original task is empty")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _validate_conversation_url(value: str) -> str:
    url = value.strip()
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.netloc.lower() not in {"chatgpt.com", "www.chatgpt.com"}
            or not parsed.path.startswith("/c/") or not parsed.path[3:].strip("/")):
        raise ActivationError("conversation URL must be an https://chatgpt.com/c/... URL")
    return url


def _validate_activation(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ActivationError("activation must be a JSON object")
    version = value.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != ACTIVATION_VERSION:
        if isinstance(version, int) and not isinstance(version, bool) and version > ACTIVATION_VERSION:
            raise UnsupportedActivationVersion(f"unsupported activation version: {version!r}")
        raise ActivationError("activation has an invalid or missing version")
    activation_id = value.get("activation_id")
    if not isinstance(activation_id, str):
        raise ActivationError("activation_id is invalid")
    try:
        parsed_id = uuid.UUID(activation_id)
    except (ValueError, AttributeError) as error:
        raise ActivationError("activation_id is invalid") from error
    if str(parsed_id) != activation_id:
        raise ActivationError("activation_id must be a canonical UUID")
    target_kind, target_value = value.get("target_kind"), value.get("target_value")
    if target_kind not in _TARGET_KINDS or not isinstance(target_value, str) or not target_value.strip():
        raise ActivationError("activation target is invalid")
    if target_kind == "conversation_url":
        target_value = _validate_conversation_url(target_value)
    else:
        target_value = target_value.strip()
        if any(character.isspace() for character in target_value):
            raise ActivationError("session ID must not contain whitespace")
    value_hash = value.get("task_hash")
    if not isinstance(value_hash, str) or not _TASK_HASH_RE.fullmatch(value_hash):
        raise ActivationError("task_hash is invalid")
    armed, consumed = value.get("armed"), value.get("consumed", False)
    if not isinstance(armed, bool) or not isinstance(consumed, bool):
        raise ActivationError("armed and consumed must be booleans")
    result = {"version": ACTIVATION_VERSION, "activation_id": activation_id,
              "target_kind": target_kind, "target_value": target_value,
              "task_hash": value_hash, "armed": armed}
    if "consumed" in value:
        result["consumed"] = consumed
    return result


def load_activation(repo_root: str | os.PathLike[str], *, required: bool = False) -> dict[str, Any] | None:
    path = activation_path(repo_root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if required:
            raise ActivationMissing("activation file does not exist")
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise ActivationError(f"invalid activation JSON: {error}") from error
    return _validate_activation(value)


def _activation_lock_path(repo_root: str | os.PathLike[str]) -> Path:
    return activation_path(repo_root).with_name("activation.lock")


def _lock_handle(handle: Any) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except (ImportError, OSError) as error:
        raise ActivationError(f"cannot acquire activation lock: {error}") from error


def _unlock_handle(handle: Any) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except (ImportError, OSError) as error:
        raise ActivationError(f"cannot release activation lock: {error}") from error


@contextmanager
def _activation_lock(repo_root: str | os.PathLike[str]):
    """Serialize Git-scoped activation mutations with an OS advisory lock."""
    path = _activation_lock_path(repo_root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
    except OSError as error:
        raise ActivationError(f"cannot open activation lock: {error}") from error
    try:
        _lock_handle(handle)
        try:
            yield
        finally:
            _unlock_handle(handle)
    finally:
        handle.close()


def save_activation(repo_root: str | os.PathLike[str], activation: Mapping[str, Any]) -> Path:
    """Atomically replace an activation file; read-modify-write callers lock."""
    value, path = _validate_activation(activation), activation_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
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


def arm(repo_root: str | os.PathLike[str], *, task: str, conversation_url: str | None = None,
        session_id: str | None = None) -> dict[str, Any]:
    if bool(conversation_url) == bool(session_id):
        raise ActivationError("provide exactly one of conversation_url or session_id")
    if conversation_url:
        target_kind, target_value = "conversation_url", _validate_conversation_url(conversation_url)
    else:
        target_kind, target_value = "session_id", str(session_id).strip()
        if not target_value or any(character.isspace() for character in target_value):
            raise ActivationError("session ID must be non-empty and contain no whitespace")
    with _activation_lock(repo_root):
        existing = load_activation(repo_root)
        if existing is not None and existing["armed"]:
            raise ActivationConflict(f"review activation already armed: {existing['activation_id']}")
        activation = {"version": ACTIVATION_VERSION, "activation_id": str(uuid.uuid4()),
                      "target_kind": target_kind, "target_value": target_value,
                      "task_hash": task_hash(task), "armed": True}
        save_activation(repo_root, activation)
        return activation


def consume(repo_root: str | os.PathLike[str], activation_id: str | None = None) -> dict[str, Any]:
    with _activation_lock(repo_root):
        activation = load_activation(repo_root, required=True)
        assert activation is not None
        if activation_id is not None and activation_id != activation["activation_id"]:
            raise ActivationError("activation_id does not match")
        activation["armed"], activation["consumed"] = False, True
        save_activation(repo_root, activation)
        return activation


def clear(repo_root: str | os.PathLike[str]) -> bool:
    with _activation_lock(repo_root):
        path = activation_path(repo_root)
        if not path.exists():
            return False
        # Do not silently delete an unreadable authorization record. Invalid or
        # future-version state must fail closed and remain available for recovery.
        load_activation(repo_root, required=True)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True


def _task_from_args(args: argparse.Namespace) -> str:
    if args.task_file:
        try:
            return Path(args.task_file).read_text(encoding="utf-8")
        except OSError as error:
            raise ActivationError(f"cannot read task file: {error}") from error
    return args.task


def _result(**value: Any) -> None:
    print(json.dumps(value, ensure_ascii=True, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    arm_parser = commands.add_parser("arm")
    targets = arm_parser.add_mutually_exclusive_group(required=True)
    targets.add_argument("--conversation-url")
    targets.add_argument("--session-id")
    task_source = arm_parser.add_mutually_exclusive_group(required=True)
    task_source.add_argument("--task-file")
    task_source.add_argument("--task")
    commands.add_parser("status")
    consume_parser = commands.add_parser("consume")
    consume_parser.add_argument("--activation-id")
    commands.add_parser("clear")
    args = parser.parse_args(argv)
    try:
        if args.command == "arm":
            activation = arm(args.repo, task=_task_from_args(args), conversation_url=args.conversation_url,
                             session_id=args.session_id)
            _result(ok=True, **activation)
        elif args.command == "status":
            _result(ok=True, activation=load_activation(args.repo))
        elif args.command == "consume":
            _result(ok=True, **consume(args.repo, args.activation_id))
        else:
            _result(ok=True, cleared=clear(args.repo))
    except (ActivationError, subprocess.CalledProcessError, OSError) as error:
        _result(ok=False, code=getattr(error, "code", "ACTIVATION_INVALID"), error=str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
