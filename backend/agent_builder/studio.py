"""Compiled graph exported for `langgraph dev` / LangSmith Studio."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from shared.tracing import apply_langsmith_aliases

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
apply_langsmith_aliases()

from backend.agent_builder.graph import build_graph
from backend.agent_builder.parent_agent import ACTIVATION_ORDER

graph = build_graph(set(ACTIVATION_ORDER))
