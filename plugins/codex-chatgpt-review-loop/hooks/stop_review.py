"""Fail-closed Stop-hook gate for an explicitly armed external review."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REVIEW_READY = "@@REVIEW_READY@@"
WEB_REVIEW_PASS = "@@WEB_REVIEW_PASS@@"
CONTEXT_BEGIN = "@@REVIEW_CONTEXT_BEGIN@@"
CONTEXT_END = "@@REVIEW_CONTEXT_END@@"
_ACTIVATION_LINE = re.compile(r"^@@REVIEW_ACTIVATION=(.*?)@@$")


def _nonempty_lines(message: str) -> list[str]:
    return [line.strip() for line in message.splitlines() if line.strip()]


def _ends_with_marker(message: str, marker: str) -> bool:
    """Accept a protocol marker only when it is the final non-empty line."""

    lines = _nonempty_lines(message)
    return bool(lines and lines[-1] == marker)


def _activation_marker(message: str) -> str | None:
    """Return one standalone activation ID, rejecting fenced/duplicate markers."""

    markers: list[str] = []
    in_fence = False
    for raw_line in message.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        match = _ACTIVATION_LINE.fullmatch(line)
        if match:
            if in_fence:
                return None
            marker = match.group(1)
            if not marker:
                return None
            markers.append(marker)
    return markers[0] if len(markers) == 1 else None


def _context_is_standalone(message: str) -> bool:
    """Context delimiters are protocol lines, not prose or code-fence content."""

    begin = end = 0
    in_fence = False
    for raw_line in message.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if line == CONTEXT_BEGIN:
            if in_fence:
                return False
            begin += 1
        elif line == CONTEXT_END:
            if in_fence:
                return False
            end += 1
    return begin == 1 and end == 1


def _load_helpers():
    """Defer all activation/context imports until the marker fast path passes."""

    scripts = Path(__file__).parents[1] / "skills" / "chatgpt-review-loop" / "scripts"
    scripts_text = str(scripts)
    if scripts_text not in sys.path:
        sys.path.insert(0, scripts_text)
    from parse_review_context import parse_review_context
    from review_activation import ActivationError, load_activation, task_hash

    return ActivationError, load_activation, parse_review_context, task_hash


def _repo_root(payload: dict[str, object]) -> Path:
    cwd = payload.get("cwd")
    return Path(cwd).resolve() if isinstance(cwd, str) and cwd else Path.cwd().resolve()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    # This is deliberately the complete normal path: no module loading, Git,
    # filesystem reads, bridge startup, or network work for ordinary stops.
    last_message = str(payload.get("last_assistant_message") or "")
    if (
        payload.get("stop_hook_active")
        or _ends_with_marker(last_message, WEB_REVIEW_PASS)
        or not _ends_with_marker(last_message, REVIEW_READY)
    ):
        print(json.dumps({}))
        return 0

    activation_id = _activation_marker(last_message)
    if not activation_id or not _context_is_standalone(last_message):
        print(json.dumps({}))
        return 0

    try:
        ActivationError, load_activation, parse_review_context, task_hash = _load_helpers()
        context = parse_review_context(last_message)
        if not context.get("ok"):
            print(json.dumps({}))
            return 0
        activation = load_activation(_repo_root(payload), required=True)
        if (
            activation is None
            or activation.get("armed") is not True
            or activation.get("activation_id") != activation_id
            or activation.get("task_hash") != task_hash(context["original_task"])
        ):
            print(json.dumps({}))
            return 0
    except Exception:
        # Corrupt files, unknown versions, invalid cwd, and parser failures
        # are all authorization failures. Never turn them into a block.
        print(json.dumps({}))
        return 0

    context_block = last_message[
        last_message.index(CONTEXT_BEGIN):last_message.index(CONTEXT_END) + len(CONTEXT_END)
    ]
    target_reference = f"{activation['target_kind']}={activation['target_value']}"
    print(json.dumps({
        "decision": "block",
        "reason": (
            "使用 chatgpt-review-loop Skill 对当前 HEAD 执行已授权的外部 ChatGPT Review。"
            "不要重复当前开发任务。\n"
            f"activation_id={activation_id}\n"
            f"review_target={target_reference}\n"
            "以下是本轮开发 context（原样传递给 Skill）：\n"
            + context_block
        ),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
