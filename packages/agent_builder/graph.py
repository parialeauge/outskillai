from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from packages.agent_builder.capex_agent import run_capex
from packages.agent_builder.financial_agent import run_financial
from packages.agent_builder.general_agent import run_general
from packages.agent_builder.parent_agent import ACTIVATION_ORDER, route
from packages.agent_builder.pm_agent import run_pm
from packages.agent_builder.specialist import failed_payload, run_with_timeout
from packages.agent_builder.state import AgentState
from shared.config import AGENT_TIMEOUT, JOB_TIMEOUT

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
        activated = route(state.get("query") or "", built, chat_sync=chat_sync)
        return {"activated": activated}

    def fanout(state: AgentState):
        activated = [name for name in (state.get("activated") or []) if name in built and name in runners]
        return [Send(name, dict(state)) for name in activated]

    def merge_node(state: AgentState) -> dict:
        order = {name: index for index, name in enumerate(ACTIVATION_ORDER)}
        findings = list(state.get("findings") or [])
        findings.sort(key=lambda item: order.get(item.get("agent"), 99))
        return {"merged_findings": findings}

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
    initial = {
        "query": query,
        "built": list(built),
        "handle": kb_handle,
        "activated": [],
        "findings": [],
        "timeline_events": [],
        "warnings": [],
        "merged_findings": [],
    }
    job_updater("running")
    try:
        result = run_with_timeout(lambda: compiled.invoke(initial), job_timeout)
    except TimeoutError:
        result = {**initial, "warnings": ["JOB_TIMEOUT"]}
    job_updater("merging")
    job_updater("formatting")
    job_updater("completed")
    return result


def _wrap_agent(name: str, fn, agent_timeout: float):
    def node(state: AgentState) -> dict:
        try:
            if agent_timeout is None or agent_timeout <= 0:
                return fn(state)
            return run_with_timeout(lambda: fn(state), agent_timeout)
        except TimeoutError:
            return failed_payload(name, error=f"AGENT_TIMEOUT after {agent_timeout}s")
        except Exception as error:
            return failed_payload(name, error=str(error))

    return node
