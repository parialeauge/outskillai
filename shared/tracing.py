"""LangSmith / LangChain tracing aliases and invoke config."""

from __future__ import annotations

import os

_TRUE = {"true", "1", "yes"}

_ALIASES = (
    ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"),
    ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
    ("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT"),
    ("LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT"),
)


def apply_langsmith_aliases() -> None:
    """Copy current LangSmith names to legacy LangChain names and the reverse."""
    for current, legacy in _ALIASES:
        left = (os.getenv(current) or "").strip()
        right = (os.getenv(legacy) or "").strip()
        if left and not right:
            os.environ[legacy] = left
        elif right and not left:
            os.environ[current] = right


def tracing_enabled() -> bool:
    apply_langsmith_aliases()
    flag = (os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2") or "").strip().lower()
    return flag in _TRUE


def run_config(*, source: str, job_id: str | None = None) -> dict:
    metadata: dict[str, str] = {"source": source}
    if job_id:
        metadata["job_id"] = job_id
    return {
        "run_name": "pactlify",
        "tags": ["pactlify", source],
        "metadata": metadata,
    }
