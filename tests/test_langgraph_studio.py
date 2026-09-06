import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_langgraph_json_declares_pactlify_graph():
    config = json.loads((ROOT / "langgraph.json").read_text())
    assert config["graphs"]["pactlify"] == "./backend/agent_builder/studio.py:graph"
    assert config["env"] in {".env", "./.env"}
    assert "." in config["dependencies"]


def test_studio_graph_exposes_route_and_specialist_nodes():
    from backend.agent_builder.studio import graph

    nodes = set(graph.get_graph().nodes)
    assert {"route", "merge", "financial", "pm", "capex", "general"} <= nodes
