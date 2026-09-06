from backend.rag_engine.classifier import classify_chunk, classify_document


def test_unmatched_document_is_uncategorized():
    def chat_sync(messages, **kwargs):
        return "uncategorized"

    assert classify_document("lorem ipsum dolor sit amet", chat_sync=chat_sync) == "uncategorized"


def test_mixed_document_chunks_get_financial_and_pm():
    budget = "Q3 revenue budget forecast ROI and operating costs"
    timeline = "project timeline milestone risk register and resource allocation"
    assert classify_chunk(budget, auto_category="pm") == "financial"
    assert classify_chunk(timeline, auto_category="uncategorized") == "pm"


def test_llm_failure_falls_back_to_heuristic_not_exception():
    def chat_sync(messages, **kwargs):
        raise RuntimeError("OpenRouter down")

    result = classify_document(
        "The project timeline and key milestones are at risk.",
        chat_sync=chat_sync,
    )
    assert result == "pm"


def test_classifier_requests_json_schema_and_accepts_json_label():
    captured: dict = {}

    def chat_sync(messages, **kwargs):
        captured.update(kwargs)
        return '{"category": "financial"}'

    assert classify_document("lorem ipsum dolor sit amet", chat_sync=chat_sync) == "financial"
    fmt = captured.get("response_format") or {}
    assert fmt.get("type") == "json_schema"
