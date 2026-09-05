from __future__ import annotations

import json
import re
import threading
from typing import Any, Callable

from shared.config import AGENT_TIMEOUT

TITLES = {
    "financial": "Financial",
    "pm": "Project Manager",
    "capex": "CapEx",
    "general": "General",
}


def should_search_live_web(
    primary_count: int,
    *,
    live_web_if_empty: bool = True,
    live_web_if_thin: int | None = None,
    needs_current_info: bool = False,
) -> bool:
    if live_web_if_empty and primary_count == 0:
        return True
    if live_web_if_thin is not None and primary_count < live_web_if_thin:
        return True
    return bool(needs_current_info)


def run_specialist(
    name: str,
    category: str | list[str],
    state: dict,
    *,
    retrieve_fn=None,
    chat_sync=None,
    web_search=None,
    live_web_if_empty: bool = True,
    live_web_if_thin: int | None = None,
    timeout: float = AGENT_TIMEOUT,
) -> dict:
    def work() -> dict:
        return _run_body(
            name,
            category,
            state,
            retrieve_fn=retrieve_fn,
            chat_sync=chat_sync,
            web_search=web_search,
            live_web_if_empty=live_web_if_empty,
            live_web_if_thin=live_web_if_thin,
        )

    try:
        if timeout is None or timeout <= 0:
            return work()
        return run_with_timeout(work, timeout)
    except TimeoutError:
        return failed_payload(name, error=f"AGENT_TIMEOUT after {timeout}s")
    except Exception as error:
        return failed_payload(name, error=str(error))


def _run_body(
    name: str,
    category: str | list[str],
    state: dict,
    *,
    retrieve_fn,
    chat_sync,
    web_search,
    live_web_if_empty: bool,
    live_web_if_thin: int | None,
) -> dict:
    warnings: list[str] = []
    llm = chat_sync
    if llm is None:
        from shared.llm import chat_sync as llm  # type: ignore[assignment]
    retriever = retrieve_fn
    if retriever is None:
        from packages.rag_engine import retrieve as retriever
    searcher = web_search
    if searcher is None:
        from packages.agent_builder.web import search_live_web as searcher

    query = str(state.get("query") or "")
    sub_question = _rewrite(name, query, llm, warnings)
    result = retriever(
        state.get("knowledge_base_id", "shared"),
        sub_question,
        category=category,
        handle=state.get("handle"),
    )
    chunks = list(getattr(result, "chunks", None) or [])
    primary_count = int(getattr(result, "primary_count", 0) or 0)
    handed_ids = [chunk.chunk_id for chunk in chunks]

    used_live_web = should_search_live_web(
        primary_count,
        live_web_if_empty=live_web_if_empty,
        live_web_if_thin=live_web_if_thin,
        needs_current_info=bool(state.get("needs_current_info")),
    )
    web_hits: list[str] = []
    if used_live_web:
        try:
            web_hits = list(searcher(sub_question) or [])
        except Exception as error:
            warnings.append(f"{name}: live web failed: {error}")
            used_live_web = False

    synthesis = _synthesize(name, query, chunks, web_hits, llm, warnings)
    used_chunk_ids = [chunk_id for chunk_id in synthesis["used_chunk_ids"] if chunk_id in handed_ids]
    title = TITLES.get(name, name)
    finding = {
        "agent": name,
        "title": title,
        "summary": synthesis["summary"],
        "body": synthesis["body"] or synthesis["summary"],
        "key_points": synthesis["key_points"],
        "evidence": synthesis["evidence"],
        "used_chunk_ids": used_chunk_ids,
        "chunks": chunks,
    }
    event = {
        "agent": name,
        "status": "done",
        "chunks_retrieved": len(chunks),
        "primary_count": primary_count,
        "used_live_web": used_live_web,
        "error": None,
    }
    return {
        "findings": [finding],
        "timeline_events": [event],
        "warnings": warnings,
    }


def run_with_timeout(fn: Callable[[], Any], timeout: float) -> Any:
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = fn()
        except Exception as error:  # noqa: BLE001
            box["error"] = error

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise TimeoutError(f"timed out after {timeout}s")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def failed_payload(name: str, error: str) -> dict:
    return {
        "findings": [],
        "timeline_events": [
            {
                "agent": name,
                "status": "failed",
                "chunks_retrieved": 0,
                "primary_count": 0,
                "used_live_web": False,
                "error": error,
            }
        ],
        "warnings": [f"{name}: {error}"],
    }


def _rewrite(name: str, query: str, chat_sync: Callable[..., str], warnings: list[str]) -> str:
    try:
        rewritten = chat_sync(
            [
                {
                    "role": "system",
                    "content": f"Rewrite the user question as a focused {name} sub-question. Reply with the sub-question only.",
                },
                {"role": "user", "content": query},
            ]
        ).strip()
        return rewritten or query
    except Exception as error:
        warnings.append(f"{name}: rewrite failed: {error}")
        return query


def _synthesize(
    name: str,
    query: str,
    chunks: list,
    web_hits: list[str],
    chat_sync: Callable[..., str],
    warnings: list[str],
) -> dict[str, Any]:
    context = _context_block(chunks, web_hits)
    try:
        raw = chat_sync(
            [
                {
                    "role": "system",
                    "content": (
                        f"You are the {TITLES.get(name, name)} specialist. "
                        "Use only the evidence. Label off-domain chunks as related material from outside this domain. "
                        "Label live-web hits as web sources. "
                        'Reply JSON: {"summary": str, "body": str, "key_points": [str], '
                        '"evidence": [str], "used_chunk_ids": [str]}.'
                    ),
                },
                {"role": "user", "content": f"Question: {query}\n\nEvidence:\n{context}"},
            ]
        )
        parsed = _parse_synthesis(raw)
    except Exception as error:
        warnings.append(f"{name}: synthesis failed: {error}")
        parsed = {}
    handed = [chunk.chunk_id for chunk in chunks]
    used = parsed.get("used_chunk_ids") or []
    if not isinstance(used, list):
        used = []
    used = [str(item) for item in used]
    summary = str(parsed.get("summary") or "")
    body = str(parsed.get("body") or summary)
    key_points = parsed.get("key_points") or []
    if not isinstance(key_points, list):
        key_points = [str(key_points)]
    evidence = parsed.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
    return {
        "summary": summary,
        "body": body,
        "key_points": [str(point) for point in key_points],
        "evidence": [str(item) for item in evidence],
        "used_chunk_ids": used if used else handed,
    }


def _context_block(chunks: list, web_hits: list[str]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        label = (
            "related material from outside this domain"
            if getattr(chunk.metadata, "cross_category", False)
            else f"in-domain {chunk.metadata.category} source"
        )
        parts.append(f"[{chunk.chunk_id}] ({label}, {chunk.metadata.source}): {chunk.content}")
    for index, hit in enumerate(web_hits, start=1):
        parts.append(f"[web_{index}] (web source): {hit}")
    return "\n".join(parts) if parts else "(no evidence)"


def _parse_synthesis(raw: str) -> dict:
    text = raw.strip()
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {"summary": text, "body": text, "key_points": [], "evidence": [], "used_chunk_ids": []}
        try:
            payload = json.loads(match.group(0))
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {"summary": text, "body": text, "key_points": [], "evidence": [], "used_chunk_ids": []}
