from packages.agent_builder.formatter import format_job
from packages.rag_engine.types import Chunk, ChunkMetadata


def _chunk(chunk_id: str, content: str, type_: str = "txt") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        metadata=ChunkMetadata(
            document_id="doc_1",
            source="charter.pdf" if type_ != "csv" else "budget.csv",
            type=type_,
            category="pm",
            auto_category="pm",
            page=1 if type_ == "pdf" else None,
            row_start=1 if type_ == "csv" else None,
            row_end=2 if type_ == "csv" else None,
            relevance=0.9,
            cross_category=False,
        ),
    )


def _finding(agent: str, used_chunk_ids: list[str]):
    return {
        "agent": agent,
        "title": agent,
        "summary": "summary",
        "body": "body",
        "key_points": ["point"],
        "used_chunk_ids": used_chunk_ids,
        "citation_ids": [],
    }


def test_invented_used_chunk_id_is_dropped():
    handed = [_chunk("chk_real", "alpha text about budget")]
    envelope = format_job(
        query="q",
        activated=["pm"],
        findings=[_finding("pm", used_chunk_ids=["chk_real", "chk_invented"])],
        handed={"pm": handed},
        warnings=[],
    )
    assert [c["id"] for c in envelope["citations"]] == ["c1"]
    assert "c2" not in {c["id"] for c in envelope["citations"]}
    assert envelope["warnings"]  # invented id dropped, warning appended


def test_two_agents_same_chunk_share_one_citation_id():
    shared = _chunk("chk_budget", "region,quarter,revenue\neast,Q1,10")
    envelope = format_job(
        query="q",
        activated=["financial", "pm"],
        findings=[
            _finding("financial", used_chunk_ids=["chk_budget"]),
            _finding("pm", used_chunk_ids=["chk_budget"]),
        ],
        handed={"financial": [shared], "pm": [shared]},
        warnings=[],
    )
    assert len(envelope["citations"]) == 1
    assert envelope["citations"][0]["id"] == "c1"
    assert envelope["answer"]["sections"][0]["citation_ids"] == ["c1"]
    assert envelope["answer"]["sections"][1]["citation_ids"] == ["c1"]


def test_csv_quote_includes_header_and_data_row():
    csv_chunk = _chunk(
        "chk_csv",
        "region,quarter,revenue,budget\neast,Q1,10,12\nwest,Q1,20,18",
        type_="csv",
    )
    envelope = format_job(
        query="q",
        activated=["financial"],
        findings=[_finding("financial", used_chunk_ids=["chk_csv"])],
        handed={"financial": [csv_chunk]},
        warnings=[],
    )
    quote = envelope["citations"][0]["quote"]
    assert "region,quarter,revenue,budget" in quote
    assert "east,Q1,10,12" in quote
    assert quote in csv_chunk.content


def test_quote_is_substring_of_chunk_content():
    chunk = _chunk("chk_txt", "The milestone slips to November if hiring freezes.")
    envelope = format_job(
        query="q",
        activated=["pm"],
        findings=[_finding("pm", used_chunk_ids=["chk_txt"])],
        handed={"pm": [chunk]},
    )
    assert envelope["citations"][0]["quote"] in chunk.content
