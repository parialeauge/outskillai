from backend.agent_builder.parent_agent import FIRST_SLICE_FALLBACK, decide, route


def test_pm_only_question_activates_pm():
    def chat_sync(messages, **kwargs):
        return '{"agents": ["pm"]}'

    assert route("What is the project timeline?", built={"pm", "financial"}, chat_sync=chat_sync) == ["pm"]


def test_finance_and_timeline_activates_both_in_stable_order():
    def chat_sync(messages, **kwargs):
        return '{"agents": ["pm", "financial"]}'

    assert route(
        "What is the timeline and financial impact?",
        built={"pm", "financial"},
        chat_sync=chat_sync,
    ) == ["financial", "pm"]


def test_unbuilt_capex_falls_back_without_crash():
    def chat_sync(messages, **kwargs):
        return '{"agents": ["capex"]}'

    assert (
        route("What capital is needed?", built={"pm", "financial"}, chat_sync=chat_sync)
        == FIRST_SLICE_FALLBACK
    )


def test_routing_failure_activates_both_before_general_exists():
    def chat_sync(messages, **kwargs):
        raise RuntimeError("down")

    assert route("anything", built={"pm", "financial"}, chat_sync=chat_sync) == FIRST_SLICE_FALLBACK


def test_routing_failure_activates_general_when_built():
    def chat_sync(messages, **kwargs):
        raise RuntimeError("down")

    assert route(
        "anything",
        built={"pm", "financial", "capex", "general"},
        chat_sync=chat_sync,
    ) == ["general"]


def test_router_requests_json_schema_response_format():
    captured: dict = {}

    def chat_sync(messages, **kwargs):
        captured.update(kwargs)
        return '{"agents": ["pm"]}'

    route("What is the project timeline?", built={"pm"}, chat_sync=chat_sync)
    fmt = captured.get("response_format") or {}
    assert fmt.get("type") == "json_schema"
    schema = (fmt.get("json_schema") or {}).get("schema") or {}
    assert "agents" in schema.get("properties", {})


def test_decide_reads_needs_current_info_from_router_json():
    def chat_sync(messages, **kwargs):
        return '{"agents": ["general"], "needs_current_info": true}'

    agents, needs = decide(
        "what happened this week?",
        built={"general", "pm"},
        chat_sync=chat_sync,
    )
    assert agents == ["general"]
    assert needs is True
