import time

from packages.agent_builder.graph import build_graph, run_job
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
    assert statuses[-1] == "completed"
