from __future__ import annotations

import json
from pathlib import Path

from packages.agent_builder.parent_agent import ACTIVATION_ORDER
from packages.rag_engine.types import Chunk

QUOTE_LIMIT = 200


def format_job(
    query: str,
    activated: list[str],
    findings: list[dict],
    handed: dict[str, list[Chunk]],
    warnings: list[str] | None = None,
    *,
    job_id: str = "job_fixture",
    pdf_available: bool = False,
) -> dict:
    warning_list = list(warnings or [])
    by_agent = {item.get("agent"): item for item in findings}
    ordered_agents = [name for name in activated if name in by_agent]
    if not ordered_agents:
        ordered_agents = [name for name in ACTIVATION_ORDER if name in by_agent]

    chunk_to_cite: dict[str, str] = {}
    citations: list[dict] = []
    sections: list[dict] = []

    for agent in ordered_agents:
        finding = by_agent[agent]
        handed_chunks = {chunk.chunk_id: chunk for chunk in handed.get(agent) or []}
        requested = list(finding.get("used_chunk_ids") or [])
        valid_ids = [chunk_id for chunk_id in requested if chunk_id in handed_chunks]
        for chunk_id in requested:
            if chunk_id not in handed_chunks:
                warning_list.append(
                    f"Dropped chunk id {chunk_id} from {agent} (not retrieved by that agent)."
                )

        citation_ids: list[str] = []
        for chunk_id in valid_ids:
            if chunk_id not in chunk_to_cite:
                cite_id = f"c{len(citations) + 1}"
                chunk_to_cite[chunk_id] = cite_id
                citations.append(_citation(cite_id, handed_chunks[chunk_id]))
            citation_ids.append(chunk_to_cite[chunk_id])

        for raw_id in finding.get("citation_ids") or []:
            if raw_id not in citation_ids:
                warning_list.append(
                    f"Dropped citation id {raw_id} from {agent} (no matching chunk)."
                )

        sections.append(
            {
                "agent": agent,
                "title": finding.get("title") or agent,
                "body": finding.get("body") or finding.get("summary") or "",
                "key_points": list(finding.get("key_points") or []),
                "citation_ids": citation_ids,
            }
        )

    summary = " ".join(
        str(by_agent[agent].get("summary") or "").strip() for agent in ordered_agents
    ).strip()
    envelope = {
        "job_id": job_id,
        "query": query,
        "activated_agents": list(activated),
        "answer": {"summary": summary, "sections": sections},
        "citations": citations,
        "warnings": warning_list,
        "pdf_available": pdf_available,
    }
    return _apply_template(envelope)


def quote_from_chunk(chunk: Chunk) -> str:
    content = chunk.content or ""
    if chunk.metadata.type != "csv":
        return content[:QUOTE_LIMIT]

    lines = content.splitlines()
    if not lines:
        return ""
    header = lines[0]
    data_lines = [line for line in lines[1:] if line.strip()]
    if not data_lines:
        return header

    quote = header
    for line in data_lines:
        candidate = f"{quote}\n{line}"
        if quote != header and len(candidate) > QUOTE_LIMIT:
            break
        quote = candidate
        if len(quote) >= QUOTE_LIMIT:
            break
    if quote == header:
        quote = f"{header}\n{data_lines[0]}"
    return quote


def _citation(cite_id: str, chunk: Chunk) -> dict:
    meta = chunk.metadata
    return {
        "id": cite_id,
        "source": meta.source,
        "type": meta.type,
        "category": meta.category,
        "page": meta.page,
        "row_start": meta.row_start,
        "row_end": meta.row_end,
        "cross_category": bool(meta.cross_category),
        "quote": quote_from_chunk(chunk),
    }


def _apply_template(envelope: dict) -> dict:
    for folder in (Path("resource"), Path("out")):
        for name in ("response.json", "template.json"):
            path = folder / name
            if not path.is_file():
                continue
            try:
                template = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(template, dict):
                return {**template, **envelope}
    return envelope
