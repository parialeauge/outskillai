"""Compiled graph exported for `langgraph dev` / LangSmith Studio."""

from __future__ import annotations

from backend.agent_builder.graph import build_graph
from backend.agent_builder.parent_agent import ACTIVATION_ORDER

graph = build_graph(set(ACTIVATION_ORDER))
