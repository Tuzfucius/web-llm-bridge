"""Make the light-weight lifecycle decision for the review loop."""

from __future__ import annotations

import json
import sys


REVIEW_READY = "@@REVIEW_READY@@"
WEB_REVIEW_PASS = "@@WEB_REVIEW_PASS@@"
CONTEXT_BEGIN = "@@REVIEW_CONTEXT_BEGIN@@"
CONTEXT_END = "@@REVIEW_CONTEXT_END@@"


def _ends_with_marker(message: str, marker: str) -> bool:
    """Accept a protocol marker only when it is the final non-empty line."""

    lines = [line.strip() for line in message.splitlines() if line.strip()]
    return bool(lines and lines[-1] == marker)


def _context_excerpt(message: str) -> str:
    """Copy the context block verbatim; do not interpret its contents."""

    start = message.find(CONTEXT_BEGIN)
    if start < 0:
        return ""
    end = message.find(CONTEXT_END, start + len(CONTEXT_BEGIN))
    if end < 0:
        return ""
    return message[start : end + len(CONTEXT_END)]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        payload = {}

    # Codex sets this flag when a stop hook is already trying to continue; do
    # not re-enter and create an unbounded loop.
    last_message = str(payload.get("last_assistant_message") or "")
    if _ends_with_marker(last_message, WEB_REVIEW_PASS):
        print(json.dumps({}))
    elif payload.get("stop_hook_active"):
        print(json.dumps({}))
    elif _ends_with_marker(last_message, REVIEW_READY):
        context = _context_excerpt(last_message)
        context_note = (
            "\n以下是本轮开发 context（原样传递给 Skill）：\n" + context
            if context
            else "\n上一条消息未包含完整 REVIEW_CONTEXT；Skill 应报告 REVIEW_CONTEXT_MISSING。"
        )
        print(json.dumps({
            "decision": "block",
            "reason": "使用 chatgpt-review-loop Skill 对当前 HEAD 执行外部 ChatGPT Review。不要重复当前开发任务。" + context_note,
        }))
    else:
        print(json.dumps({}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
