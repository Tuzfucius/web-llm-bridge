"""Deterministic parser for the two-stage external review protocol."""

from __future__ import annotations

from typing import Any


PASS_MARKER = "@@CODEX_REVIEW_STATUS=PASS@@"
REVISE_MARKER = "@@CODEX_REVIEW_STATUS=REVISE@@"
PROMPT_BEGIN = "@@CODEX_PROMPT_BEGIN@@"
PROMPT_END = "@@CODEX_PROMPT_END@@"


def parse_review(text: str) -> dict[str, Any]:
    """Return PASS/REVISE only when exactly one status marker is present."""

    source = text if isinstance(text, str) else str(text or "")
    pass_count = source.count(PASS_MARKER)
    revise_count = source.count(REVISE_MARKER)
    if pass_count == 1 and revise_count == 0:
        return {"ok": True, "status": "PASS"}
    if pass_count == 0 and revise_count == 1:
        return {"ok": True, "status": "REVISE"}
    return {
        "ok": False,
        "status": "PROTOCOL_ERROR",
        "error": "expected exactly one PASS or REVISE marker",
    }


def parse_codex_prompt(text: str) -> dict[str, Any]:
    """Extract a non-empty Codex prompt bounded by the required markers."""

    source = text if isinstance(text, str) else str(text or "")
    begin = source.count(PROMPT_BEGIN)
    end = source.count(PROMPT_END)
    if begin != 1 or end != 1:
        return {"ok": False, "status": "PROTOCOL_ERROR", "error": "missing or duplicate prompt markers"}
    start = source.index(PROMPT_BEGIN) + len(PROMPT_BEGIN)
    finish = source.find(PROMPT_END, start)
    if finish < 0:
        return {"ok": False, "status": "PROTOCOL_ERROR", "error": "prompt markers are out of order"}
    prompt = source[start:finish].strip()
    if not prompt:
        return {"ok": False, "status": "PROTOCOL_ERROR", "error": "empty Codex prompt"}
    return {"ok": True, "status": "REVISE", "codex_prompt": prompt}


__all__ = [
    "PASS_MARKER",
    "REVISE_MARKER",
    "PROMPT_BEGIN",
    "PROMPT_END",
    "parse_review",
    "parse_codex_prompt",
]
