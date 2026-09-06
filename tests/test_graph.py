import time

from backend.agent_builder.graph import build_graph, run_job
from backend.agent_builder.pm_agent import run_pm
from backend.agent_builder.specialist import run_with_timeout
from backend.rag_engine.types import RetrieveResult
from shared.config import AGENT_TIMEOUT, JOB_TIMEOUT


def _financial(state):
    return {
        "findings": [{"agent": "financial", "summary": "money"}],
        "timeline_events": [{"agent": "financial", "status": "done", "error": None}],
        "warnings": [],
    }


def _pm(state):
    return {
        "findings": [{"agent": "pm", "summary": "dates"}],
        "timeline_events": [{"agent": "pm", "status": "done", "error": None}],
        "warnings": [],
    }


def _pm_raises(state):
    raise RuntimeError("pm boom")


def _chat_both(messages, **kwargs):
    return '{"agents": ["pm", "financial"]}'


def test_two_agents_findings_concatenated_in_activation_order():
    graph = build_graph(
        {"financial", "pm"},
        agents={"financial": _financial, "pm": _pm},
        chat_sync=_chat_both,
    )
    out = graph.invoke({"query": "timeline and budget?", "built": ["financial", "pm"]})
    assert [item["agent"] for item in out["merged_findings"]] == ["financial", "pm"]
    assert {item["agent"] for item in out["findings"]} == {"financial", "pm"}


def test_one_agent_raising_still_returns_the_other():
    graph = build_graph(
        {"financial", "pm"},
        agents={"financial": _financial, "pm": _pm_raises},
        chat_sync=_chat_both,
    )
    out = graph.invoke({"query": "q", "built": ["financial", "pm"]})
    assert [item["agent"] for item in out["merged_findings"]] == ["financial"]
    statuses = {event["agent"]: event["status"] for event in out["timeline_events"]}
    assert statuses["pm"] == "failed"
    assert statuses["financial"] == "done"


def test_four_sequential_agent_timeouts_fit_job_budget():
    assert 4 * AGENT_TIMEOUT < JOB_TIMEOUT


def test_agent_timeout_is_failed_and_does_not_stall_job():
    def hang(state):
        time.sleep(2)
        return {
            "findings": [{"agent": "pm", "summary": "late"}],
            "timeline_events": [{"agent": "pm", "status": "done", "error": None}],
            "warnings": [],
        }

    graph = build_graph(
        {"pm"},
        agents={"pm": hang},
        chat_sync=lambda messages, **kwargs: '{"agents": ["pm"]}',
        agent_timeout=0.1,
    )
    started = time.monotonic()
    out = graph.invoke({"query": "q", "built": ["pm"]})
    assert time.monotonic() - started < 1.0
    assert out["timeline_events"][0]["status"] == "failed"
    assert out["merged_findings"] == []


def test_job_timeout_keeps_findings_from_agents_that_finished():
    def hang(state):
        time.sleep(2)
        return {
            "findings": [{"agent": "pm", "summary": "late"}],
            "timeline_events": [{"agent": "pm", "status": "done", "error": None}],
            "warnings": [],
        }

    graph = build_graph(
        {"financial", "pm"},
        agents={"financial": _financial, "pm": hang},
        chat_sync=_chat_both,
        agent_timeout=5,
    )
    out = run_job("q", None, lambda status, **kwargs: None, built={"financial", "pm"}, graph=graph, job_timeout=0.4)
    assert [item["agent"] for item in out["merged_findings"]] == ["financial"]
    assert "JOB_TIMEOUT" in out["warnings"]
    assert out["timeline_events"][0]["agent"] == "financial"


def test_graph_does_not_nest_a_second_specialist_timeout_thread(monkeypatch):
    calls: list[float] = []
    real = run_with_timeout

    def spy(fn, timeout):
        calls.append(timeout)
        return real(fn, timeout)

    monkeypatch.setattr("backend.agent_builder.graph.run_with_timeout", spy)
    monkeypatch.setattr("backend.agent_builder.specialist.run_with_timeout", spy)

    def retrieve_fn(*args, **kwargs):
        return RetrieveResult(chunks=[], primary_count=1)

    graph = build_graph(
        {"pm"},
        agents={"pm": lambda state: run_pm(state, retrieve_fn=retrieve_fn, web_search=lambda query: [], chat_sync=lambda messages, **kwargs: '{"summary":"s","body":"b","key_points":[],"used_chunk_ids":[]}')},
        chat_sync=lambda messages, **kwargs: '{"agents": ["pm"]}',
        agent_timeout=5,
    )
    graph.invoke({"query": "q", "built": ["pm"]})
    assert calls == [5]


def test_run_job_writes_status_sequence_and_enforces_job_timeout():
    statuses: list[str] = []

    def updater(status: str, **kwargs):
        statuses.append(status)

    def hang(state):
        time.sleep(2)
        return {"findings": [], "timeline_events": [], "warnings": []}

    graph = build_graph(
        {"pm"},
        agents={"pm": hang},
        chat_sync=lambda messages, **kwargs: '{"agents": ["pm"]}',
        agent_timeout=5,
    )
    started = time.monotonic()
    run_job("q", None, updater, built={"pm"}, graph=graph, job_timeout=0.2)
    assert time.monotonic() - started < 1.5
    assert statuses[0] == "queued"
    assert statuses[1] == "routing"
    assert "running" in statuses
    assert "merging" in statuses
    assert "formatting" in statuses
    assert statuses[-1] == "formatting"
    assert "completed" not in statuses


def test_route_sets_needs_current_info_on_state():
    graph = build_graph(
        {"general"},
        agents={"general": lambda state: {"findings": [], "timeline_events": [], "warnings": []}},
        chat_sync=lambda messages, **kwargs: '{"agents": ["general"], "needs_current_info": true}',
    )
    out = graph.invoke({"query": "what happened this week?", "built": ["general"]})
    assert out.get("needs_current_info") is True
    assert out.get("activated") == ["general"]
