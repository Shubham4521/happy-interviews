"""Branded PDF export (ReportLab).

Turns the report's markdown into a clean document: gradient header band,
a details block, colored text tags instead of icons (Source / Your profile /
AI tip), clickable citation numbers, and a numbered source list.
"""
import io
import re
import unicodedata
from datetime import date
from urllib.parse import urlparse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, HRFlowable, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

INK = colors.HexColor("#161A35")
MUTED = colors.HexColor("#5A6183")
LINE = colors.HexColor("#E3E7F3")
INDIGO = colors.HexColor("#4F46E5")
VIOLET = colors.HexColor("#7C3AED")
SKY = colors.HexColor("#0EA5E9")

TAGS = {
    "🌐": ("Source", "#1D6FE0", "#E8F1FE"),
    "💼": ("Your profile", "#6D28D9", "#F1EAFE"),
    "💡": ("AI tip", "#4A5473", "#EEF0F6"),
}
PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
BAND_H = 46 * mm

STYLES = {
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14.5,
                           textColor=INK, spaceAfter=3),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=15, leading=19,
                         textColor=INK, spaceBefore=14, spaceAfter=4, keepWithNext=1),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11, leading=15,
                         textColor=INDIGO, spaceBefore=8, spaceAfter=3, keepWithNext=1),
    "meta_label": ParagraphStyle("ml", fontName="Helvetica", fontSize=8.5, leading=11,
                                 textColor=MUTED),
    "meta_value": ParagraphStyle("mv", fontName="Helvetica-Bold", fontSize=10, leading=13,
                                 textColor=INK),
    "note": ParagraphStyle("note", fontName="Helvetica", fontSize=9.5, leading=13.5,
                           textColor=colors.HexColor("#7A4B00")),
    "source": ParagraphStyle("src", fontName="Helvetica", fontSize=9, leading=12.5,
                             textColor=INK, leftIndent=16, bulletIndent=0, spaceAfter=3),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, leading=12,
                            textColor=MUTED),
}


def _bullet_style(level: int) -> ParagraphStyle:
    return ParagraphStyle(f"b{level}", parent=STYLES["body"], leftIndent=14 + 14 * level,
                          bulletIndent=2 + 14 * level, spaceAfter=2.5)


class CheckItem(Flowable):
    """A checklist line: an empty rounded square drawn as vector art, then the text.
    (Symbol fonts aren't embedded in every PDF viewer, so we draw the box ourselves.)"""

    def __init__(self, markup: str, level: int = 0):
        super().__init__()
        self.offset = 16 + 14 * level
        self.para = Paragraph(markup, ParagraphStyle("check", parent=STYLES["body"], spaceAfter=0))

    def wrap(self, avail_w, avail_h):
        _, self.para_h = self.para.wrap(avail_w - self.offset, avail_h)
        return avail_w, self.para_h + 3

    def draw(self):
        c = self.canv
        c.setStrokeColor(MUTED)
        c.setLineWidth(0.9)
        box_top = self.para_h + 3 - 3.2
        c.roundRect(self.offset - 13, box_top - 8, 8, 8, 1.6, stroke=1, fill=0)
        self.para.drawOn(c, self.offset, 3)


def _pdf_safe(text: str) -> str:
    """Drops emoji and characters the built-in PDF fonts can't draw."""
    text = (text or "").replace("₹", "Rs. ").replace("‍", "")
    out = []
    for ch in text:
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            plain = unicodedata.normalize("NFKD", ch).encode("cp1252", "ignore").decode("cp1252")
            out.append(plain)
    return "".join(out)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _tag(label: str, fg: str, bg: str) -> str:
    return (f'<font name="Helvetica-Bold" size="7.5" color="{fg}" backColor="{bg}">'
            f"&nbsp;{label}&nbsp;</font>&nbsp;&nbsp;")


def _inline(text: str, source_urls: dict) -> str:
    """Markdown inline -> ReportLab mini-HTML, with tags and clickable citations."""
    for emoji, (label, _, _) in TAGS.items():
        text = text.replace(emoji, f"\x00{label}\x00")
    text = _escape(_pdf_safe(text)).strip()

    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                  lambda m: f'<link href="{m.group(2)}" color="#4F46E5">{m.group(1)}</link>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)

    def cite(m):
        n = int(m.group(1))
        url = _escape(source_urls[n]) if n in source_urls else None
        label = f'<font size="7.5" color="#4F46E5"><super>[{n}]</super></font>'
        return f'<link href="{url}">{label}</link>' if url else label

    text = re.sub(r"\[(\d+)\]", cite, text)
    for label, fg, bg in TAGS.values():
        text = text.replace(f"\x00{label}\x00", _tag(label, fg, bg))
    return text


def _note_box(text: str, source_urls: dict) -> Table:
    box = Table([[Paragraph(_inline(text, source_urls), STYLES["note"])]],
                colWidths=[PAGE_W - 2 * MARGIN])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF8EB")),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, colors.HexColor("#F59E0B")),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return box


def markdown_to_flowables(md: str, source_urls: dict) -> list:
    flow = []
    for raw in (md or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        indent = (len(line) - len(line.lstrip(" "))) // 2
        stripped = line.strip()

        if m := re.match(r"#{1,6}\s+(.*)", stripped):
            flow.append(Paragraph(_inline(m.group(1), source_urls), STYLES["h3"]))
        elif m := re.match(r">\s?(.*)", stripped):
            flow.append(_note_box(m.group(1), source_urls))
            flow.append(Spacer(1, 4))
        elif m := re.match(r"[-*+]\s+\[[ xX]?\]\s+(.*)", stripped):
            flow.append(CheckItem(_inline(m.group(1), source_urls), min(indent, 2)))
        elif m := re.match(r"[-*+]\s+(.*)", stripped):
            flow.append(Paragraph(_inline(m.group(1), source_urls), _bullet_style(min(indent, 2)),
                                  bulletText="•"))
        elif m := re.match(r"(\d+)[.)]\s+(.*)", stripped):
            flow.append(Paragraph(_inline(m.group(2), source_urls), _bullet_style(min(indent, 2)),
                                  bulletText=f"{m.group(1)}."))
        else:
            flow.append(Paragraph(_inline(stripped, source_urls), STYLES["body"]))
    return flow


def _draw_gradient(c, x, y, w, h):
    c.saveState()
    path = c.beginPath()
    path.rect(x, y, w, h)
    c.clipPath(path, stroke=0, fill=0)
    try:
        c.linearGradient(x, y + h, x + w, y, (INDIGO, VIOLET, SKY), extend=False)
    except Exception:
        c.setFillColor(INDIGO)
        c.rect(x, y, w, h, stroke=0, fill=1)
    c.restoreState()


def build_pdf(company: str, role: str, location: str, profile: dict,
              results: dict, sections: dict, sources: list) -> bytes:
    """Returns the PDF as bytes."""
    company, role, location = (_pdf_safe(s) for s in (company, role, location))
    source_urls = {s["num"]: s["url"] for s in sources}
    today = date.today().strftime("%d %b %Y")
    buffer = io.BytesIO()

    def first_page(c, doc):
        _draw_gradient(c, 0, PAGE_H - BAND_H, PAGE_W, BAND_H)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, PAGE_H - 14 * mm, "HappyInterviews")
        c.setFont("Helvetica", 9)
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - 14 * mm, f"Interview prep report  |  {today}")
        c.setFont("Helvetica-Bold", 24)
        c.drawString(MARGIN, PAGE_H - 30 * mm, company[:48])
        c.setFont("Helvetica", 12)
        c.drawString(MARGIN, PAGE_H - 38 * mm, f"{role} in {location}"[:80])
        footer(c, doc)

    def later_page(c, doc):
        _draw_gradient(c, 0, PAGE_H - 4, PAGE_W, 4)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8.5)
        c.drawString(MARGIN, PAGE_H - 11 * mm, f"{company}  |  {role}"[:90])
        footer(c, doc)

    def footer(c, doc):
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.line(MARGIN, 13 * mm, PAGE_W - MARGIN, 13 * mm)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN, 9 * mm, "Generated by HappyInterviews. Verify key facts using the linked sources.")
        c.drawRightString(PAGE_W - MARGIN, 9 * mm, f"Page {doc.page}")

    doc = BaseDocTemplate(buffer, pagesize=A4, title=f"{company} interview prep report",
                          author="HappyInterviews", leftMargin=MARGIN, rightMargin=MARGIN)
    frame_w = PAGE_W - 2 * MARGIN
    first = Frame(MARGIN, 18 * mm, frame_w, PAGE_H - BAND_H - 26 * mm, id="first")
    later = Frame(MARGIN, 18 * mm, frame_w, PAGE_H - 36 * mm, id="later")
    doc.addPageTemplates([
        PageTemplate(id="First", frames=[first], onPage=first_page, autoNextPageTemplate="Later"),
        PageTemplate(id="Later", frames=[later], onPage=later_page),
    ])

    story = []
    details = [("Company", company), ("Role", role), ("Location", location)]
    if profile.get("level") and profile["level"] != "Not specified":
        details.append(("Experience", profile["level"]))
    if profile.get("round") and profile["round"] != "All rounds":
        details.append(("Round", profile["round"]))
    cells = [[Paragraph(_escape(k), STYLES["meta_label"]) for k, _ in details],
             [Paragraph(_escape(_pdf_safe(v)), STYLES["meta_value"]) for _, v in details]]
    meta = Table(cells, colWidths=[frame_w / len(details)] * len(details))
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F7FD")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [meta, Spacer(1, 8)]

    legend = ("How to read this report: " + _tag(*TAGS["🌐"]) + "points come from the web, with a "
              "numbered link to the page. " + _tag(*TAGS["💼"]) + "points come from your resume or job "
              "description. " + _tag(*TAGS["💡"]) + "points are AI suggestions.")
    story += [Paragraph(legend, STYLES["small"]), Spacer(1, 4)]

    for key, cfg in sections.items():
        result = results.get(key) or {}
        story.append(Paragraph(_escape(cfg["title"]), STYLES["h2"]))
        story.append(HRFlowable(width="100%", thickness=1.2, color=INDIGO, spaceBefore=0,
                                spaceAfter=6))
        story += markdown_to_flowables(result.get("text", ""), source_urls)

    if sources:
        story.append(Paragraph("Sources", STYLES["h2"]))
        story.append(HRFlowable(width="100%", thickness=1.2, color=INDIGO, spaceAfter=6))
        for s in sources:
            domain = urlparse(s["url"]).netloc.replace("www.", "")
            title = _escape(_pdf_safe(s["title"]))[:160]
            story.append(Paragraph(
                f'<link href="{_escape(s["url"])}" color="#161A35">{title}</link> '
                f'<font color="#5A6183">({_escape(domain)})</font>',
                STYLES["source"], bulletText=f"{s['num']}."))

    doc.build(story)
    return buffer.getvalue()
