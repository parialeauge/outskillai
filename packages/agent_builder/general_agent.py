from __future__ import annotations

from packages.agent_builder.specialist import run_specialist
from shared.config import GENERAL_THIN_PRIMARY


def run_general(state: dict, **kwargs) -> dict:
    return run_specialist(
        "general",
        ["uncategorized", "policy"],
        state,
        live_web_if_empty=False,
        live_web_if_thin=GENERAL_THIN_PRIMARY,
        **kwargs,
    )
