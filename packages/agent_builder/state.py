from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    query: str
    built: list[str]
    activated: list[str]
    handle: Any
    findings: Annotated[list, operator.add]
    timeline_events: Annotated[list, operator.add]
    warnings: Annotated[list, operator.add]
    merged_findings: list
    needs_current_info: bool
    progress: Any
