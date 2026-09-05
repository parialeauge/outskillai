from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from io import BytesIO

_WEASY_HTML = None
try:
    from weasyprint import HTML as _WEASY_HTML
except Exception:  # system libs (cairo/pango) often missing
    _WEASY_HTML = None

_A4_MM_WIDTH = 210
_SIDE_MM = 16
_USABLE_MM = _A4_MM_WIDTH - (2 * _SIDE_MM)


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
    <html>
    <head>
      <meta charset="utf-8"/>
      <style>
        @page {{
          size: A4;
          margin: 16mm 16mm 20mm 16mm;
          @bottom-center {{
            content: "Page " counter(page) " of " counter(pages);
            font-family: Times, "Times New Roman", serif;
            font-size: 9pt;
          }}
        }}
        body {{
          font-family: Times, "Times New Roman", serif;
          font-size: 11pt;
          line-height: 1.35;
          overflow-wrap: anywhere;
          word-wrap: break-word;
        }}
        h1 {{ font-size: 18pt; margin: 0 0 8pt; }}
        h2 {{ font-size: 13pt; margin: 14pt 0 6pt; }}
        p {{ margin: 0 0 8pt; white-space: pre-wrap; }}
        ul {{ margin: 0 0 8pt; padding-left: 16pt; }}
        table {{
          width: 100%;
          table-layout: fixed;
          border-collapse: collapse;
          font-size: 9.5pt;
        }}
        td, th {{
          border: 0.4pt solid #999;
          padding: 4pt 5pt;
          vertical-align: top;
          overflow-wrap: anywhere;
          word-break: break-word;
        }}
      </style>
    </head>
    <body>
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
    </body>
    </html>
    """


def _reportlab_pdf(envelope: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    answer = envelope.get("answer") or {}
    body_style = ParagraphStyle(
        "PactlifyBody",
        fontName="Times-Roman",
        fontSize=11,
        leading=14,
        spaceAfter=6,
    )
    heading_style = ParagraphStyle(
        "PactlifyHeading",
        fontName="Times-Bold",
        fontSize=13,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
    )
    title_style = ParagraphStyle(
        "PactlifyTitle",
        fontName="Times-Bold",
        fontSize=18,
        leading=22,
        spaceAfter=8,
    )
    small_style = ParagraphStyle(
        "PactlifySmall",
        fontName="Times-Roman",
        fontSize=9,
        leading=12,
    )

    story: list = [
        Paragraph("Pactlify", title_style),
        Paragraph(_flow_text(f"Date: {date}"), body_style),
        Paragraph(_flow_text(f"Job: {envelope.get('job_id') or ''}"), body_style),
        Paragraph(_flow_text(f"Query: {envelope.get('query') or ''}"), body_style),
        Paragraph("Summary", heading_style),
        Paragraph(_flow_text(answer.get("summary") or ""), body_style),
    ]
    for section in answer.get("sections") or []:
        story.append(Paragraph(_flow_text(section.get("title") or section.get("agent")), heading_style))
        story.append(Paragraph(_flow_text(section.get("body") or ""), body_style))
        for point in section.get("key_points") or []:
            story.append(Paragraph(_flow_text(f"• {point}"), body_style))
        cites = ", ".join(str(item) for item in section.get("citation_ids") or [])
        if cites:
            story.append(Paragraph(_flow_text(f"Citations: {cites}"), body_style))

    story.append(Paragraph("Citations", heading_style))
    cite_rows = [[_cell("ID", small_style), _cell("Source", small_style), _cell("Quote", small_style)]]
    for citation in envelope.get("citations") or []:
        cite_rows.append(
            [
                _cell(citation.get("id"), small_style),
                _cell(citation.get("source"), small_style),
                _cell(citation.get("quote") or "", small_style),
            ]
        )
    story.append(_table(cite_rows, [18 * mm, 45 * mm, (_USABLE_MM - 63) * mm]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Sources", heading_style))
    source_rows = [
        [
            _cell("ID", small_style),
            _cell("Source", small_style),
            _cell("Type", small_style),
            _cell("Category", small_style),
            _cell("Cross", small_style),
        ]
    ]
    for citation in envelope.get("citations") or []:
        source_rows.append(
            [
                _cell(citation.get("id"), small_style),
                _cell(citation.get("source"), small_style),
                _cell(citation.get("type"), small_style),
                _cell(citation.get("category"), small_style),
                _cell("CROSS" if citation.get("cross_category") else "", small_style),
            ]
        )
    story.append(_table(source_rows, [18 * mm, 50 * mm, 22 * mm, 40 * mm, (_USABLE_MM - 130) * mm]))

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=_SIDE_MM * mm,
        rightMargin=_SIDE_MM * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title="Pactlify",
    )
    document.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()


def _flow_text(text: object) -> str:
    broken = _soft_break(str(text or ""))
    return escape(broken).replace("\n", "<br/>").replace("\u200b", "&#8203;")


def _soft_break(text: str, limit: int = 48) -> str:
    parts: list[str] = []
    for token in text.split(" "):
        if len(token) <= limit:
            parts.append(token)
            continue
        chunks = [token[index : index + limit] for index in range(0, len(token), limit)]
        parts.append("\u200b".join(chunks))
    return " ".join(parts)


def _cell(value: object, style) -> Paragraph:
    from reportlab.platypus import Paragraph

    return Paragraph(_flow_text(value), style)


def _table(rows: list, widths: list):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.93, 0.93, 0.93)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.Color(0.6, 0.6, 0.6)),
            ]
        )
    )
    return table


class _NumberedCanvas:
    """ReportLab canvas that stamps 'Page N of M' after the page count is known."""

    def __new__(cls, *args, **kwargs):
        from reportlab.pdfgen.canvas import Canvas

        class _Canvas(Canvas):
            def __init__(self, *inner_args, **inner_kwargs):
                Canvas.__init__(self, *inner_args, **inner_kwargs)
                self._saved_page_states: list[dict] = []

            def showPage(self):
                self._saved_page_states.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                page_count = len(self._saved_page_states)
                for state in self._saved_page_states:
                    self.__dict__.update(state)
                    self._draw_page_number(page_count)
                    Canvas.showPage(self)
                Canvas.save(self)

            def _draw_page_number(self, page_count: int) -> None:
                from reportlab.lib.pagesizes import A4
                from reportlab.lib.units import mm

                width, _height = A4
                self.setFont("Times-Roman", 9)
                self.drawCentredString(
                    width / 2,
                    10 * mm,
                    f"Page {self._pageNumber} of {page_count}",
                )

        return _Canvas(*args, **kwargs)
