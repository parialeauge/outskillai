from __future__ import annotations

from packages.agent_builder.specialist import run_specialist


def run_capex(state: dict, **kwargs) -> dict:
    return run_specialist("capex", "capex", state, live_web_if_empty=True, **kwargs)
