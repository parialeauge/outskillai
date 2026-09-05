from packages.agent_builder.pdf_generator import render_pdf, safe_render


def _envelope():
    return {
        "job_id": "job_fixture",
        "query": "What is the timeline?",
        "activated_agents": ["pm"],
        "answer": {
            "summary": "Hiring freeze delays the milestone.",
            "sections": [
                {
                    "agent": "pm",
                    "title": "Project Manager",
                    "body": "November slip if hiring stays frozen.",
                    "key_points": ["November slip risk"],
                    "citation_ids": ["c1"],
                }
            ],
        },
        "citations": [
            {
                "id": "c1",
                "source": "charter.pdf",
                "type": "pdf",
                "category": "pm",
                "page": 1,
                "row_start": None,
                "row_end": None,
                "cross_category": False,
                "quote": "The milestone slips to November",
            }
        ],
        "warnings": [],
        "pdf_available": False,
    }


def test_render_pdf_bytes_start_with_percent_pdf():
    data = render_pdf(_envelope())
    assert data.startswith(b"%PDF")


def test_safe_render_does_not_raise_when_renderer_fails(monkeypatch):
    def boom(envelope):
        raise RuntimeError("cairo missing")

    monkeypatch.setattr("packages.agent_builder.pdf_generator.render_pdf", boom)
    data, available, warnings = safe_render(_envelope())
    assert data is None
    assert available is False
    assert warnings
