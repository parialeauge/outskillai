import pymupdf
from reportlab.lib.pagesizes import A4

from packages.agent_builder.pdf_generator import _html, _reportlab_pdf, render_pdf, safe_render

TAIL = "UNIQUE_PDF_TAIL_ZX9"
A4_WIDTH, A4_HEIGHT = A4


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


def _long_envelope(*, repeats: int = 8):
    body = ("Detailed justification of each CapEx line item including vendor, amount, and date. " * repeats) + TAIL
    quote = (
        "vendor,amount,delivery\n"
        "Acme Robotics,125000,2026-03-01\n"
        + ("Northwind Steel,88000,2026-04-15\n" * 4)
        + TAIL
    )
    env = _envelope()
    env["query"] = "What is the full CapEx plan for FY26 including every vendor and milestone?"
    env["answer"]["summary"] = body
    env["answer"]["sections"][0]["body"] = body
    env["answer"]["sections"][0]["key_points"] = [body]
    env["citations"][0]["quote"] = quote
    return env


def _pdf_text(data: bytes) -> str:
    document = pymupdf.open(stream=data, filetype="pdf")
    return "\n".join(page.get_text() for page in document)


def _assert_a4(data: bytes) -> None:
    document = pymupdf.open(stream=data, filetype="pdf")
    rect = document[0].rect
    assert abs(rect.width - A4_WIDTH) < 2
    assert abs(rect.height - A4_HEIGHT) < 2


def test_reportlab_keeps_full_text_on_a4_with_page_numbers():
    data = _reportlab_pdf(_long_envelope(repeats=40))
    assert data.startswith(b"%PDF")
    _assert_a4(data)
    document = pymupdf.open(stream=data, filetype="pdf")
    assert document.page_count >= 2
    extracted = _pdf_text(data)
    assert TAIL in extracted
    for index, page in enumerate(document, start=1):
        footer = page.get_text(
            clip=pymupdf.Rect(0, page.rect.height - 48, page.rect.width, page.rect.height)
        )
        assert f"Page {index} of {document.page_count}" in footer


def test_render_pdf_keeps_full_text_on_a4():
    data = render_pdf(_long_envelope())
    _assert_a4(data)
    assert TAIL in _pdf_text(data)


def test_html_template_declares_a4_and_page_numbers():
    markup = _html(_envelope())
    assert "size: A4" in markup
    assert "counter(page)" in markup


def test_safe_render_does_not_raise_when_renderer_fails(monkeypatch):
    def boom(envelope):
        raise RuntimeError("cairo missing")

    monkeypatch.setattr("packages.agent_builder.pdf_generator.render_pdf", boom)
    data, available, warnings = safe_render(_envelope())
    assert data is None
    assert available is False
    assert warnings
