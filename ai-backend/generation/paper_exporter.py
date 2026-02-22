"""
Paper Export Service - PDF/DOCX Generation

Exports question papers in proper university exam format with:
- Header (Subject, College, Marks)
- Instructions to candidates
- MCQ questions with options (4 per page)
- Descriptive questions
- Separate answer key and marking scheme documents

Mathematical expressions in LaTeX notation (\\( ... \\) inline, \\[ ... \\] display)
are rendered to PNG images via matplotlib mathtext and embedded inline in the PDF.
"""

import logging
import re
from pathlib import Path
from typing import Optional, List, Tuple

from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import inch, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, KeepTogether, Flowable, Image as RLImage,
)
from reportlab.lib import colors
from generation.schemas import PaperOutput

log = logging.getLogger(__name__)

# Max width for diagram images in the question paper (cm)
FIGURE_MAX_WIDTH_CM = 14
FIGURE_MAX_HEIGHT_CM = 12


# ─── Math rendering helpers ──────────────────────────────────────────────────────

def _escape_html(text: str) -> str:
    """Escape HTML special characters so ReportLab Paragraph treats them as literal text."""
    if not text:
        return text or ""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _strip_graph_tags(text: str) -> Tuple[str, List]:
    """
    Remove all [GRAPH: ...] tags from text and return:
      (clean_text_without_graph_tags, list_of_RLImage_flowables)

    The caller appends the flowables directly to the story after the Paragraph.
    Returns (text, []) when no graph tags are present.
    """
    try:
        from generation import graph_renderer
    except ImportError:
        return text, []

    if not graph_renderer.has_graph_tag(text):
        return text, []

    from generation.graph_renderer import extract_graph_tags, render_graph_to_png

    flowables = []
    text_parts = []

    for span in extract_graph_tags(text):
        if span["type"] == "text":
            text_parts.append(span["content"])
        else:
            # Render graph and collect as RLImage flowable
            result = render_graph_to_png(span["spec"])
            if result is not None:
                png_path, w_pts, h_pts = result
                # Cap to page width (A4 ≈ 450 pts usable)
                max_w = 14 * 28.35  # 14cm in pts
                if w_pts > max_w:
                    scale = max_w / w_pts
                    w_pts = max_w
                    h_pts *= scale
                try:
                    flowables.append(RLImage(png_path, width=w_pts, height=h_pts))
                except Exception as e:
                    log.warning("paper_exporter: could not create RLImage for graph: %s", e)
                    text_parts.append(f"[Graph: {span['spec'][:40]}...]")
            else:
                # Fallback: show the raw tag as text
                text_parts.append(f"[Graph diagram]")

    return "".join(text_parts).strip(), flowables


def _render_math_in_text(text: str, fontsize: int = 11) -> str:
    """
    Convert LaTeX math spans in LLM-generated text to inline ReportLab <img> tags.

    Plain-text portions are HTML-escaped so that characters like < and & do not
    break ReportLab's XML parser.  Double newlines become <br/> paragraph breaks;
    single newlines become spaces (ReportLab reflows text).

    Falls back to showing the raw expression in square brackets if matplotlib is
    unavailable or rendering fails.

    Only call this on raw LLM-generated content (question_text, option.text,
    answer_key, marking scheme points) — not on strings that already contain
    ReportLab markup tags.
    """
    if not text:
        return ""

    try:
        from generation import math_renderer  # lazy import
    except ImportError:
        log.warning("math_renderer not available; falling back to HTML-escaped text")
        return _escape_html(text)

    if not math_renderer.has_math(text):
        result = _escape_html(text)
        result = re.sub(r'\n{2,}', '<br/>', result)
        result = result.replace('\n', ' ')
        return result

    spans = math_renderer.extract_math_spans(text)
    parts = []  # type: list

    for span in spans:
        if span["type"] == "text":
            chunk = _escape_html(span["content"])
            chunk = re.sub(r'\n{2,}', '<br/>', chunk)
            chunk = chunk.replace('\n', ' ')
            parts.append(chunk)
        else:
            rendered = math_renderer.render_latex_to_png_safe(
                span["expr"],
                fontsize=fontsize,
                display=span["display"],
            )
            if rendered is not None:
                png_path, w_pts, h_pts = rendered
                # Cap height so large display formulas don't overflow a line
                max_h = fontsize * 3.0
                if h_pts > max_h:
                    scale = max_h / h_pts
                    w_pts *= scale
                    h_pts = max_h
                img_tag = (
                    f'<img src="{png_path}" width="{w_pts:.1f}" '
                    f'height="{h_pts:.1f}" valign="middle"/>'
                )
                if span["display"]:
                    parts.append(f"<br/>{img_tag}<br/>")
                else:
                    parts.append(img_tag)
            else:
                # Fallback: show expression in brackets as readable plain text
                clean = _escape_html(span["expr"])
                parts.append(f"[{clean}]")

    return "".join(parts)


# ─── Configuration ──────────────────────────────────────────────────────────────

DEFAULT_COLLEGE_NAME = "University/College Name"
DEFAULT_INSTRUCTIONS = [
    "Figures to the right indicate full marks.",
    "Use of scientific calculator is allowed.",
    "Use suitable data wherever required.",
    "All questions are compulsory.",
]


# ─── Custom Flowables ───────────────────────────────────────────────────────────

class HorizontalLine(Flowable):
    """Draw a horizontal line across the page."""
    
    def __init__(self, width, thickness=1, color=colors.black):
        Flowable.__init__(self)
        self.width = width
        self.thickness = thickness
        self.color = color
    
    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self.width, 0)


# ─── Style Definitions ──────────────────────────────────────────────────────────

def get_custom_styles():
    """Define custom paragraph styles for the exam paper."""
    styles = getSampleStyleSheet()
    
    # Header styles
    styles.add(ParagraphStyle(
        name='CollegeName',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.black,
        alignment=TA_CENTER,
        spaceAfter=6,
        fontName='Helvetica-Bold',
    ))
    
    styles.add(ParagraphStyle(
        name='SubjectName',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.black,
        alignment=TA_CENTER,
        spaceAfter=4,
        fontName='Helvetica-Bold',
    ))
    
    styles.add(ParagraphStyle(
        name='ExamDetails',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.black,
        alignment=TA_CENTER,
        spaceAfter=12,
        fontName='Helvetica',
    ))
    
    # Section headers
    styles.add(ParagraphStyle(
        name='SectionHeader',
        parent=styles['Heading3'],
        fontSize=12,
        textColor=colors.black,
        alignment=TA_LEFT,
        spaceAfter=8,
        spaceBefore=12,
        fontName='Helvetica-Bold',
    ))
    
    # Question styles
    styles.add(ParagraphStyle(
        name='QuestionText',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.black,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
        fontName='Helvetica',
        leading=14,
    ))
    
    styles.add(ParagraphStyle(
        name='MCQOption',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        alignment=TA_LEFT,
        leftIndent=20,
        spaceAfter=4,
        fontName='Helvetica',
    ))
    
    styles.add(ParagraphStyle(
        name='Instructions',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        alignment=TA_LEFT,
        leftIndent=30,
        spaceAfter=4,
        fontName='Helvetica',
    ))
    
    # Answer key styles
    styles.add(ParagraphStyle(
        name='AnswerText',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
        leftIndent=10,
        fontName='Helvetica',
        leading=13,
    ))
    
    return styles


# ─── Question Paper Generator ───────────────────────────────────────────────────

def generate_question_paper(
    paper: PaperOutput,
    subject_name: str,
    college_name: Optional[str] = None,
    additional_instructions: Optional[list] = None,
    question_image_paths: Optional[List[List[str]]] = None,
) -> BytesIO:
    """
    Generate question paper PDF (questions only, no answers).
    question_image_paths: optional list of image path lists, one per question (section/variant order).
    When present, figures are drawn below the corresponding question text.
    Returns BytesIO buffer containing the PDF.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )
    
    styles = get_custom_styles()
    story = []
    
    # ─── Header ─────────────────────────────────────────────────────────────────
    college = college_name or DEFAULT_COLLEGE_NAME
    story.append(Paragraph(college, styles['CollegeName']))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(f"<b>{subject_name}</b>", styles['SubjectName']))
    story.append(Spacer(1, 0.1*cm))
    story.append(Paragraph(f"Total Marks: {paper.total_marks}", styles['ExamDetails']))
    story.append(Spacer(1, 0.3*cm))
    
    # Horizontal line
    story.append(HorizontalLine(width=16*cm, thickness=1.5))
    story.append(Spacer(1, 0.3*cm))
    
    # ─── Instructions ───────────────────────────────────────────────────────────
    story.append(Paragraph("<b>Instructions to Candidates:</b>", styles['Normal']))
    story.append(Spacer(1, 0.2*cm))
    
    instructions = additional_instructions or DEFAULT_INSTRUCTIONS
    for i, instruction in enumerate(instructions, 1):
        story.append(Paragraph(f"{i}) {instruction}", styles['Instructions']))
    
    story.append(Spacer(1, 0.3*cm))
    story.append(HorizontalLine(width=16*cm, thickness=1.5))
    story.append(Spacer(1, 0.5*cm))
    
    # ─── Questions ──────────────────────────────────────────────────────────────
    q_image_iter = iter(question_image_paths or [])
    def _next_images():
        return next(q_image_iter, [])
    
    for section in paper.sections:
        # Each section is one question (may have OR variants)
        
        # For OR questions, show both variants
        if len(section.variants) > 1:
            # OR question
            or_variants = []
            for variant in section.variants:
                q = variant.question
                clean_q_text, graph_flowables = _strip_graph_tags(q.question_text)
                rendered_q = _render_math_in_text(clean_q_text, fontsize=11)
                marks_text = f"({q.marks} marks)" if q.marks else ""
                q_text = f"<b>{variant.variant_label}.</b> {rendered_q}"
                if marks_text:
                    q_text += f" <b>{marks_text}</b>"
                or_variants.append(Paragraph(q_text, styles['QuestionText']))
                for gf in graph_flowables:
                    or_variants.append(Spacer(1, 0.2*cm))
                    or_variants.append(gf)

                # MCQ options for this variant
                if q.question_type == "mcq" and q.options:
                    for option in q.options:
                        opt_text = f"<b>{option.label}.</b> {_render_math_in_text(option.text, fontsize=10)}"
                        or_variants.append(Paragraph(opt_text, styles['MCQOption']))
                    or_variants.append(Spacer(1, 0.3*cm))
                # Diagram images for this variant (one list per variant)
                variant_images = _next_images()
                for img_path in variant_images:
                    if Path(img_path).exists():
                        try:
                            img = RLImage(img_path, width=FIGURE_MAX_WIDTH_CM*cm, height=FIGURE_MAX_HEIGHT_CM*cm)
                            or_variants.append(Spacer(1, 0.2*cm))
                            or_variants.append(img)
                        except Exception:
                            pass
                or_variants.append(Spacer(1, 0.3*cm))
            
            # Add instruction text for OR
            or_note = Paragraph("<i>(Attempt any one)</i>", styles['Normal'])
            story.append(or_note)
            story.append(Spacer(1, 0.2*cm))
            
            # Add all variants
            for item in or_variants:
                story.append(item)
            story.append(Spacer(1, 0.5*cm))
        else:
            # Regular question (single variant)
            variant = section.variants[0]
            q = variant.question
            
            # Question number and text — strip graph tags before inline rendering
            clean_q_text, graph_flowables = _strip_graph_tags(q.question_text)
            q_num = f"<b>Q{section.question_no}.</b>" if not variant.variant_label else f"<b>{variant.variant_label}.</b>"
            rendered_q = _render_math_in_text(clean_q_text, fontsize=11)
            marks_text = f"({q.marks} marks)" if q.marks else ""
            q_text = f"{q_num} {rendered_q}"
            if marks_text:
                q_text += f" <b>{marks_text}</b>"
            
            story.append(Paragraph(q_text, styles['QuestionText']))
            # Embed graph diagrams below question text
            for gf in graph_flowables:
                story.append(Spacer(1, 0.2*cm))
                story.append(gf)
            
            # MCQ options
            if q.question_type == "mcq" and q.options:
                story.append(Spacer(1, 0.2*cm))
                for option in q.options:
                    opt_text = f"<b>{option.label}.</b> {_render_math_in_text(option.text, fontsize=10)}"
                    story.append(Paragraph(opt_text, styles['MCQOption']))
            
            # Diagram images (source_assets)
            for img_path in _next_images():
                if Path(img_path).exists():
                    try:
                        story.append(Spacer(1, 0.2*cm))
                        img = RLImage(img_path, width=FIGURE_MAX_WIDTH_CM*cm, height=FIGURE_MAX_HEIGHT_CM*cm)
                        story.append(img)
                    except Exception:
                        pass
            
            story.append(Spacer(1, 0.5*cm))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer


# ─── Answer Key Generator ───────────────────────────────────────────────────────

def generate_answer_key(
    paper: PaperOutput,
    subject_name: str,
    college_name: Optional[str] = None,
) -> BytesIO:
    """
    Generate answer key PDF (questions + answers + marking schemes).
    
    Returns BytesIO buffer containing the PDF.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )
    
    styles = get_custom_styles()
    story = []
    
    # ─── Header ─────────────────────────────────────────────────────────────────
    college = college_name or DEFAULT_COLLEGE_NAME
    story.append(Paragraph(college, styles['CollegeName']))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(f"<b>{subject_name} - ANSWER KEY</b>", styles['SubjectName']))
    story.append(Spacer(1, 0.1*cm))
    story.append(Paragraph(f"Total Marks: {paper.total_marks}", styles['ExamDetails']))
    story.append(Spacer(1, 0.3*cm))
    story.append(HorizontalLine(width=16*cm, thickness=1.5))
    story.append(Spacer(1, 0.5*cm))
    
    # ─── Answers ────────────────────────────────────────────────────────────────
    for section in paper.sections:
        # Each section is one question (may have OR variants)
        for variant in section.variants:
            q = variant.question

            # ── Question heading ─────────────────────────────────────────────
            q_num = f"Q{section.question_no}" if not variant.variant_label else variant.variant_label
            story.append(Paragraph(
                f"<b>{q_num}.</b> ({q.marks} marks)",
                styles['QuestionText']
            ))

            # ── Question text (with graphs stripped to flowables) ────────────
            clean_q_text, graph_flowables = _strip_graph_tags(q.question_text)
            story.append(Paragraph(
                _render_math_in_text(clean_q_text, fontsize=11),
                styles['QuestionText']
            ))
            for gf in graph_flowables:
                story.append(Spacer(1, 0.2*cm))
                story.append(gf)

            # MCQ: show all options then highlight the correct one
            if q.question_type == "mcq" and q.options:
                story.append(Spacer(1, 0.1*cm))
                for option in q.options:
                    is_correct = option.label == q.answer_key
                    prefix = f"<b>✓ {option.label}.</b> " if is_correct else f"{option.label}. "
                    opt_style = styles['AnswerText'] if not is_correct else ParagraphStyle(
                        name=f'CorrectOpt_{option.label}',
                        parent=styles['AnswerText'],
                        textColor=colors.HexColor("#1a7a1a"),
                        fontName='Helvetica-Bold',
                    )
                    story.append(Paragraph(
                        prefix + _render_math_in_text(option.text, fontsize=10),
                        opt_style,
                    ))
                story.append(Spacer(1, 0.15*cm))
                story.append(Paragraph(
                    f"<b>Correct Answer: {q.answer_key}</b>",
                    styles['AnswerText']
                ))

            # Descriptive: model answer + marking scheme
            else:
                if q.answer_key:
                    story.append(Spacer(1, 0.15*cm))
                    story.append(Paragraph("<b>Model Answer:</b>", styles['Normal']))
                    story.append(Spacer(1, 0.1*cm))
                    story.append(Paragraph(_render_math_in_text(q.answer_key, fontsize=10), styles['AnswerText']))

                if q.marking_scheme:
                    story.append(Spacer(1, 0.2*cm))
                    story.append(Paragraph("<b>Marking Scheme:</b>", styles['Normal']))
                    story.append(Spacer(1, 0.1*cm))
                    for point in q.marking_scheme:
                        scheme_text = f"• {_render_math_in_text(point.point, fontsize=10)} — <b>{point.marks} mark(s)</b>"
                        story.append(Paragraph(scheme_text, styles['AnswerText']))

            story.append(Spacer(1, 0.2*cm))
            story.append(HorizontalLine(width=16*cm, thickness=0.5, color=colors.HexColor("#cccccc")))
            story.append(Spacer(1, 0.3*cm))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer


# ─── Marking Scheme Generator ───────────────────────────────────────────────────

def generate_marking_scheme(
    paper: PaperOutput,
    subject_name: str,
    college_name: Optional[str] = None,
) -> BytesIO:
    """
    Generate marking scheme PDF (detailed rubric for evaluators).
    
    Returns BytesIO buffer containing the PDF.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )
    
    styles = get_custom_styles()
    story = []
    
    # ─── Header ─────────────────────────────────────────────────────────────────
    college = college_name or DEFAULT_COLLEGE_NAME
    story.append(Paragraph(college, styles['CollegeName']))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(f"<b>{subject_name} - MARKING SCHEME</b>", styles['SubjectName']))
    story.append(Spacer(1, 0.1*cm))
    story.append(Paragraph(f"Total Marks: {paper.total_marks}", styles['ExamDetails']))
    story.append(Spacer(1, 0.3*cm))
    story.append(HorizontalLine(width=16*cm, thickness=1.5))
    story.append(Spacer(1, 0.5*cm))
    
    # ─── Marking Details ────────────────────────────────────────────────────────
    cell_style = styles['AnswerText']

    def _scheme_table(marking_scheme) -> Table:
        """Build a marking-scheme Table with math-rendered point cells."""
        table_data = [
            [Paragraph("<b>Marking Point</b>", cell_style), Paragraph("<b>Marks</b>", cell_style)]
        ]
        for pt in marking_scheme:
            table_data.append([
                Paragraph(_render_math_in_text(pt.point, fontsize=9), cell_style),
                Paragraph(str(pt.marks), cell_style),
            ])
        total = sum(p.marks for p in marking_scheme)
        table_data.append([
            Paragraph("<b>Total</b>", cell_style),
            Paragraph(f"<b>{total}</b>", cell_style),
        ])
        tbl = Table(table_data, colWidths=[12*cm, 2*cm])
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        return tbl

    def _append_question_text(story, q, q_label: str, marks: int, bloom: str):
        """Append the question heading + question text + any graph flowables to story."""
        q_type = "MCQ" if q.question_type == "mcq" else "Descriptive"
        story.append(Paragraph(
            f"<b>{q_label}</b> ({q_type}, {marks} marks, Bloom: {bloom.title()})",
            styles['QuestionText']
        ))
        # Question text
        clean_q_text, graph_flowables = _strip_graph_tags(q.question_text)
        story.append(Paragraph(
            _render_math_in_text(clean_q_text, fontsize=11),
            styles['QuestionText']
        ))
        for gf in graph_flowables:
            story.append(Spacer(1, 0.2*cm))
            story.append(gf)

    for section in paper.sections:
        # Handle OR questions (multiple variants) vs single questions
        if len(section.variants) > 1:
            story.append(Paragraph(f"<b>Q{section.question_no}. (OR Question — any one variant)</b>", styles['QuestionText']))
            story.append(Spacer(1, 0.2*cm))

            for variant in section.variants:
                q = variant.question
                _append_question_text(story, q, f"{variant.variant_label}.", section.marks, section.bloom_level)

                if q.question_type == "mcq":
                    story.append(Paragraph(
                        f"Correct answer: <b>{q.answer_key}</b> ({section.marks} marks for correct, 0 for incorrect)",
                        styles['AnswerText']
                    ))
                else:
                    if q.marking_scheme:
                        story.append(Spacer(1, 0.1*cm))
                        story.append(_scheme_table(q.marking_scheme))

                story.append(Spacer(1, 0.2*cm))
        else:
            variant = section.variants[0]
            q = variant.question
            _append_question_text(story, q, f"Q{section.question_no}.", section.marks, section.bloom_level)

            if q.question_type == "mcq":
                story.append(Paragraph(
                    f"Correct answer: <b>{q.answer_key}</b> ({section.marks} marks for correct, 0 for incorrect)",
                    styles['AnswerText']
                ))
            else:
                if q.marking_scheme:
                    story.append(Spacer(1, 0.1*cm))
                    story.append(_scheme_table(q.marking_scheme))

        story.append(Spacer(1, 0.2*cm))
        story.append(HorizontalLine(width=16*cm, thickness=0.5, color=colors.HexColor("#cccccc")))
        story.append(Spacer(1, 0.3*cm))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer
