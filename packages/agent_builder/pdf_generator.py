from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from io import BytesIO

_WEASY_HTML = None
try:
    from weasyprint import HTML as _WEASY_HTML
except Exception:  # system libs (cairo/pango) often missing
    _WEASY_HTML = None


def render_pdf(envelope: dict) -> bytes:
    if _WEASY_HTML is not None:
        try:
            return _WEASY_HTML(string=_html(envelope)).write_pdf()
        except Exception:
            pass
    return _reportlab_pdf(envelope)


def safe_render(envelope: dict) -> tuple[bytes | None, bool, list[str]]:
    try:
        data = render_pdf(envelope)
        if not data or not data.startswith(b"%PDF"):
            raise ValueError("renderer did not return a PDF")
        return data, True, []
    except Exception as error:
        return None, False, [f"PDF render failed: {error}"]


def _html(envelope: dict) -> str:
    answer = envelope.get("answer") or {}
    citations = envelope.get("citations") or []
    sections = answer.get("sections") or []
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    section_html = []
    for section in sections:
        points = "".join(f"<li>{escape(str(point))}</li>" for point in section.get("key_points") or [])
        cites = ", ".join(escape(str(item)) for item in section.get("citation_ids") or [])
        section_html.append(
            f"<h2>{escape(str(section.get('title') or section.get('agent')))}</h2>"
            f"<p>{escape(str(section.get('body') or ''))}</p>"
            f"<ul>{points}</ul>"
            f"<p>Citations: {cites}</p>"
        )
    cite_rows = []
    source_rows = []
    for citation in citations:
        cite_rows.append(
            "<tr>"
            f"<td>{escape(str(citation.get('id')))}</td>"
            f"<td>{escape(str(citation.get('source')))}</td>"
            f"<td>{escape(str(citation.get('quote') or ''))}</td>"
            "</tr>"
        )
        source_rows.append(
            "<tr>"
            f"<td>{escape(str(citation.get('id')))}</td>"
            f"<td>{escape(str(citation.get('source')))}</td>"
            f"<td>{escape(str(citation.get('type')))}</td>"
            f"<td>{escape(str(citation.get('category')))}</td>"
            f"<td>{'CROSS' if citation.get('cross_category') else ''}</td>"
            "</tr>"
        )
    return f"""
    <html><body>
      <h1>Pactlify</h1>
      <p>Date: {escape(date)}</p>
      <p>Job: {escape(str(envelope.get('job_id') or ''))}</p>
      <p>Query: {escape(str(envelope.get('query') or ''))}</p>
      <h2>Summary</h2>
      <p>{escape(str(answer.get('summary') or ''))}</p>
      {''.join(section_html)}
      <h2>Citations</h2>
      <table>{''.join(cite_rows)}</table>
      <h2>Sources</h2>
      <table>{''.join(source_rows)}</table>
    </body></html>
    """


def _reportlab_pdf(envelope: dict) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - inch
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    answer = envelope.get("answer") or {}

    def line(text: str, size: int = 11, gap: int = 16) -> None:
        nonlocal y
        if y < inch:
            page.showPage()
            y = height - inch
        page.setFont("Times-Roman", size)
        page.drawString(inch, y, text[:110])
        y -= gap

    line("Pactlify", size=18, gap=22)
    line(f"Date: {date}")
    line(f"Job: {envelope.get('job_id') or ''}")
    line(f"Query: {envelope.get('query') or ''}")
    line("Summary", size=14, gap=18)
    line(str(answer.get("summary") or ""))
    for section in answer.get("sections") or []:
        line(str(section.get("title") or section.get("agent")), size=14, gap=18)
        line(str(section.get("body") or ""))
        for point in section.get("key_points") or []:
            line(f"- {point}")
        cites = ", ".join(str(item) for item in section.get("citation_ids") or [])
        if cites:
            line(f"Citations: {cites}")
    line("Citations", size=14, gap=18)
    for citation in envelope.get("citations") or []:
        line(f"{citation.get('id')}: {citation.get('source')} — {citation.get('quote') or ''}")
    line("Sources", size=14, gap=18)
    for citation in envelope.get("citations") or []:
        cross = " CROSS" if citation.get("cross_category") else ""
        line(
            f"{citation.get('id')} | {citation.get('source')} | "
            f"{citation.get('type')} | {citation.get('category')}{cross}"
        )
    page.save()
    return buffer.getvalue()
