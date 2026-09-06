from __future__ import annotations

import threading
import time

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from backend.agent_builder.capex_agent import run_capex
from backend.agent_builder.financial_agent import run_financial
from backend.agent_builder.general_agent import run_general
from backend.agent_builder.parent_agent import ACTIVATION_ORDER, decide
from backend.agent_builder.pm_agent import run_pm
from backend.agent_builder.specialist import failed_payload, run_with_timeout
from backend.agent_builder.state import AgentState
from shared.config import AGENT_TIMEOUT, JOB_TIMEOUT
from shared.tracing import run_config

DEFAULT_AGENTS = {
    "financial": run_financial,
    "pm": run_pm,
    "capex": run_capex,
    "general": run_general,
}


def build_graph(
    built_agents: set[str],
    *,
    agents: dict | None = None,
    chat_sync=None,
    agent_timeout: float = AGENT_TIMEOUT,
):
    runners = {**DEFAULT_AGENTS, **(agents or {})}
    built = set(built_agents)
    graph = StateGraph(AgentState)

    def route_node(state: AgentState) -> dict:
        activated, needs = decide(state.get("query") or "", built, chat_sync=chat_sync)
        return {"activated": activated, "needs_current_info": needs}

    def fanout(state: AgentState):
        activated = [name for name in (state.get("activated") or []) if name in built and name in runners]
        return [Send(name, dict(state)) for name in activated]

    def merge_node(state: AgentState) -> dict:
        return {"merged_findings": _sorted_findings(state.get("findings") or [])}

    graph.add_node("route", route_node)
    graph.add_node("merge", merge_node)
    for name in built:
        if name not in runners:
            continue
        graph.add_node(name, _wrap_agent(name, runners[name], agent_timeout))
        graph.add_edge(name, "merge")

    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", fanout, list(built & set(runners)))
    graph.add_edge("merge", END)
    return graph.compile()


def run_job(
    query: str,
    kb_handle,
    job_updater,
    *,
    built: set[str],
    graph=None,
    chat_sync=None,
    job_timeout: float = JOB_TIMEOUT,
    **kwargs,
) -> dict:
    compiled = graph or build_graph(built, chat_sync=chat_sync, **kwargs)
    job_updater("queued")
    job_updater("routing")
    progress = _new_progress()
    initial = {
        "query": query,
        "built": list(built),
        "handle": kb_handle,
        "activated": [],
        "findings": [],
        "timeline_events": [],
        "warnings": [],
        "merged_findings": [],
        "needs_current_info": False,
        "progress": progress,
    }
    job_updater("running")
    try:
        result = run_with_timeout(
            lambda: compiled.invoke(initial, config=run_config(source="fastapi")),
            job_timeout,
        )
    except TimeoutError:
        result = _result_from_progress(initial, progress)
    result.pop("progress", None)
    job_updater("merging")
    job_updater("formatting")
    return result


def _wrap_agent(name: str, fn, agent_timeout: float):
    def node(state: AgentState) -> dict:
        payload = dict(state)
        progress = state.get("progress")
        try:
            if agent_timeout is None or agent_timeout <= 0:
                out = fn(payload)
            else:
                payload["deadline"] = time.monotonic() + agent_timeout

                def work():
                    value = fn(payload)
                    _record_progress(progress, value)
                    return value

                out = run_with_timeout(work, agent_timeout)
                return out
        except TimeoutError:
            out = failed_payload(name, error=f"AGENT_TIMEOUT after {agent_timeout}s")
        except Exception as error:
            out = failed_payload(name, error=str(error))
        _record_progress(progress, out)
        return out

    return node


def _new_progress() -> dict:
    return {
        "lock": threading.Lock(),
        "findings": [],
        "timeline_events": [],
        "warnings": [],
    }


def _record_progress(progress: dict | None, payload: dict) -> None:
    if not progress:
        return
    with progress["lock"]:
        progress["findings"].extend(payload.get("findings") or [])
        progress["timeline_events"].extend(payload.get("timeline_events") or [])
        progress["warnings"].extend(payload.get("warnings") or [])


def _result_from_progress(initial: dict, progress: dict) -> dict:
    with progress["lock"]:
        findings = list(progress["findings"])
        timeline = list(progress["timeline_events"])
        warnings = list(progress["warnings"])
    if "JOB_TIMEOUT" not in warnings:
        warnings.append("JOB_TIMEOUT")
    findings = _sorted_findings(findings)
    return {
        **initial,
        "findings": findings,
        "timeline_events": timeline,
        "warnings": warnings,
        "merged_findings": findings,
        "activated": [item.get("agent") for item in findings if item.get("agent")],
    }


def _sorted_findings(findings: list) -> list:
    order = {name: index for index, name in enumerate(ACTIVATION_ORDER)}
    ranked = list(findings)
    ranked.sort(key=lambda item: order.get(item.get("agent"), 99))
    return ranked
