from packages.agent_builder.capex_agent import run_capex
from packages.agent_builder.financial_agent import run_financial
from packages.agent_builder.general_agent import run_general
from packages.agent_builder.pm_agent import run_pm
from packages.rag_engine.types import Chunk, ChunkMetadata, RetrieveResult
from shared.config import GENERAL_THIN_PRIMARY


def _chunk(chunk_id: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content="timeline milestone",
        metadata=ChunkMetadata(
            document_id="d",
            source="a.txt",
            type="txt",
            category="pm",
            auto_category="pm",
        ),
    )


def test_empty_primary_triggers_web_search():
    called = []

    def retrieve_fn(*args, **kwargs):
        return RetrieveResult(chunks=[], primary_count=0)

    def web_search(query: str):
        called.append(query)
        return ["web hit"]

    def chat_sync(messages, **kwargs):
        return "ok"

    out = run_pm(
        {"query": "timeline?"},
        retrieve_fn=retrieve_fn,
        web_search=web_search,
        chat_sync=chat_sync,
    )
    assert called
    assert out["timeline_events"][0]["used_live_web"] is True


def test_nonempty_primary_skips_web_search():
    called = []
    chunk = _chunk("chk_1")

    def retrieve_fn(*args, **kwargs):
        return RetrieveResult(chunks=[chunk], primary_count=1)

    def web_search(query: str):
        called.append(query)
        return []

    def chat_sync(messages, **kwargs):
        return '{"summary": "s", "key_points": ["k"], "used_chunk_ids": ["chk_1", "invented"]}'

    out = run_financial(
        {"query": "budget?"},
        retrieve_fn=retrieve_fn,
        web_search=web_search,
        chat_sync=chat_sync,
    )
    assert called == []
    used = out["findings"][0]["used_chunk_ids"]
    assert used == ["chk_1"]
    assert "invented" not in used
    assert out["timeline_events"][0]["used_live_web"] is False


def test_capex_empty_primary_triggers_web_search():
    called = []

    def retrieve_fn(*args, **kwargs):
        assert kwargs.get("category") == "capex"
        return RetrieveResult(chunks=[], primary_count=0)

    def web_search(query: str):
        called.append(query)
        return ["web hit"]

    out = run_capex(
        {"query": "capex?"},
        retrieve_fn=retrieve_fn,
        web_search=web_search,
        chat_sync=lambda messages, **kwargs: "ok",
    )
    assert called
    assert out["timeline_events"][0]["used_live_web"] is True


def test_general_uses_uncategorized_and_policy_filter():
    seen = {}
    chunk = _chunk("chk_1")

    def retrieve_fn(*args, **kwargs):
        seen["category"] = kwargs.get("category")
        return RetrieveResult(chunks=[chunk], primary_count=GENERAL_THIN_PRIMARY)

    out = run_general(
        {"query": "summarize?"},
        retrieve_fn=retrieve_fn,
        web_search=lambda query: seen.setdefault("web", []).append(query) or [],
        chat_sync=lambda messages, **kwargs: '{"summary": "s", "used_chunk_ids": ["chk_1"]}',
    )
    assert set(seen["category"]) == {"uncategorized", "policy"}
    assert "web" not in seen
    assert out["timeline_events"][0]["used_live_web"] is False


def test_general_thin_primary_triggers_web_search():
    called = []

    def retrieve_fn(*args, **kwargs):
        return RetrieveResult(chunks=[_chunk("chk_1")], primary_count=GENERAL_THIN_PRIMARY - 1)

    def web_search(query: str):
        called.append(query)
        return ["web hit"]

    out = run_general(
        {"query": "summarize?"},
        retrieve_fn=retrieve_fn,
        web_search=web_search,
        chat_sync=lambda messages, **kwargs: "ok",
    )
    assert called
    assert out["timeline_events"][0]["used_live_web"] is True


def test_general_needs_current_info_triggers_web_search():
    called = []

    def retrieve_fn(*args, **kwargs):
        return RetrieveResult(chunks=[_chunk("chk_1")], primary_count=5)

    def web_search(query: str):
        called.append(query)
        return ["web hit"]

    out = run_general(
        {"query": "what happened this week?", "needs_current_info": True},
        retrieve_fn=retrieve_fn,
        web_search=web_search,
        chat_sync=lambda messages, **kwargs: "ok",
    )
    assert called
    assert out["timeline_events"][0]["used_live_web"] is True
