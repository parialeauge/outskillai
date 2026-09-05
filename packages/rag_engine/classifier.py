from __future__ import annotations

import re
from collections import Counter

from packages.rag_engine.types import Category

KEYWORDS: dict[str, tuple[str, ...]] = {
    "financial": ("revenue", "budget", "roi", "cost", "profit", "forecast", "operating"),
    "pm": ("timeline", "milestone", "risk", "charter", "schedule", "resource", "allocation"),
    "capex": ("capex", "capital", "depreciation", "asset", "investment"),
}

ALLOWED: set[str] = {"financial", "pm", "capex", "uncategorized"}
CHUNK_THRESHOLD = 2


def classify_document(text: str, chat_sync=None) -> Category:
    snippet = text[:2000]
    llm = chat_sync
    if llm is None:
        from shared.llm import chat_sync as llm  # type: ignore[assignment]
    try:
        raw = llm(
            [{"role": "user", "content": _doc_prompt(snippet)}],
            timeout=30,
        )
        parsed = _parse_label(raw)
        if parsed is not None:
            return parsed
    except Exception:
        pass
    return _heuristic(snippet)


def classify_chunk(text: str, auto_category: str) -> str:
    scores = _score(text)
    if not scores:
        return auto_category if auto_category in ALLOWED or auto_category == "policy" else "uncategorized"
    label, count = scores.most_common(1)[0]
    if count >= CHUNK_THRESHOLD:
        return label
    return auto_category


def _doc_prompt(snippet: str) -> str:
    return (
        "Classify this document as exactly one of: financial, pm, capex, uncategorized.\n"
        "Reply with only that label.\n\n"
        f"{snippet}"
    )


def _parse_label(raw: str) -> Category | None:
    token = raw.strip().split()[0].strip(".,:;").lower() if raw.strip() else ""
    if token in ALLOWED:
        return token  # type: ignore[return-value]
    return None


def _heuristic(text: str) -> Category:
    scores = _score(text)
    if not scores:
        return "uncategorized"
    label, count = scores.most_common(1)[0]
    if count >= 1:
        return label  # type: ignore[return-value]
    return "uncategorized"


def _score(text: str) -> Counter[str]:
    words = set(re.findall(r"[a-z]+", text.lower()))
    scores: Counter[str] = Counter()
    for label, keys in KEYWORDS.items():
        hit = sum(1 for key in keys if key in words)
        if hit:
            scores[label] = hit
    return scores
