"""Deterministic parser for the context Codex attaches to a review-ready turn."""

from __future__ import annotations

from typing import Any


CONTEXT_BEGIN = "@@REVIEW_CONTEXT_BEGIN@@"
CONTEXT_END = "@@REVIEW_CONTEXT_END@@"
_HEADINGS = {
    "Original task:": "original_task",
    "Implementation summary:": "implementation_summary",
    "Tests:": "tests",
}


def parse_review_context(text: str) -> dict[str, Any]:
    """Extract the three required plain-text sections without interpretation."""

    source = text if isinstance(text, str) else str(text or "")
    if source.count(CONTEXT_BEGIN) != 1 or source.count(CONTEXT_END) != 1:
        return {"ok": False, "code": "REVIEW_CONTEXT_MISSING"}
    start = source.index(CONTEXT_BEGIN) + len(CONTEXT_BEGIN)
    end = source.find(CONTEXT_END, start)
    if end < start:
        return {"ok": False, "code": "REVIEW_CONTEXT_MISSING"}
    body = source[start:end].strip()
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        heading = _HEADINGS.get(line.strip())
        if heading:
            if heading in sections:
                return {"ok": False, "code": "REVIEW_CONTEXT_MISSING"}
            current = heading
            sections[heading] = []
            continue
        if current is not None:
            sections[current].append(line)

    values = {key: "\n".join(lines).strip() for key, lines in sections.items()}
    if any(not values.get(key) for key in _HEADINGS.values()):
        return {"ok": False, "code": "REVIEW_CONTEXT_MISSING"}
    return {
        "ok": True,
        "original_task": values["original_task"],
        "implementation_summary": values["implementation_summary"],
        "tests": values["tests"],
    }


__all__ = ["CONTEXT_BEGIN", "CONTEXT_END", "parse_review_context"]
