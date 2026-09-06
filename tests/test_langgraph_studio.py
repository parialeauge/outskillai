import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_langgraph_json_declares_pactlify_graph():
    config = json.loads((ROOT / "langgraph.json").read_text())
    graph = config["graphs"]["pactlify"]
    path = graph["path"] if isinstance(graph, dict) else graph
    assert path == "./backend/agent_builder/studio.py:graph"
    assert config["env"] in {".env", "./.env"}
    assert config["python_version"] == "3.12"
    assert "." in config["dependencies"]


def test_rag_engine_types_import_does_not_load_lancedb():
    script = (
        "import sys, backend.rag_engine.types as types\n"
        "assert types.Chunk\n"
        "assert 'backend.rag_engine.vectorstore' not in sys.modules\n"
        "assert 'backend.rag_engine.retriever' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_studio_graph_exposes_route_and_specialist_nodes():
    from backend.agent_builder.studio import graph

    nodes = set(graph.get_graph().nodes)
    assert {"route", "merge", "financial", "pm", "capex", "general"} <= nodes
