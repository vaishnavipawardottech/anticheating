"""
Paper Export Service - PDF/DOCX Generation

Exports question papers in proper university exam format with:
- Header (Subject, College, Marks)
- Instructions to candidates
- MCQ questions with options (4 per page)
- Descriptive questions
- Separate answer key and marking scheme documents
"""

from typing import Optional
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import inch, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, KeepTogether, Flowable
)
from reportlab.lib import colors
from generation.schemas import PaperOutput


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
) -> BytesIO:
    """
    Generate question paper PDF (questions only, no answers).
    
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
    for section in paper.sections:
        # Each section is one question (may have OR variants)
        
        # For OR questions, show both variants
        if len(section.variants) > 1:
            # OR question
            or_variants = []
            for variant in section.variants:
                q = variant.question
                q_text = f"<b>{variant.variant_label}.</b> {q.question_text}"
                marks_text = f"({q.marks} marks)" if q.marks else ""
                if marks_text:
                    q_text += f" <b>{marks_text}</b>"
                or_variants.append(Paragraph(q_text, styles['QuestionText']))
                
                # MCQ options for this variant
                if q.question_type == "mcq" and q.options:
                    for option in q.options:
                        opt_text = f"<b>{option.label}.</b> {option.text}"
                        or_variants.append(Paragraph(opt_text, styles['MCQOption']))
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
            
            # Question number and text
            q_num = f"<b>Q{section.question_no}.</b>" if not variant.variant_label else f"<b>{variant.variant_label}.</b>"
            q_text = f"{q_num} {q.question_text}"
            marks_text = f"({q.marks} marks)" if q.marks else ""
            
            if marks_text:
                q_text += f" <b>{marks_text}</b>"
            
            story.append(Paragraph(q_text, styles['QuestionText']))
            
            # MCQ options
            if q.question_type == "mcq" and q.options:
                story.append(Spacer(1, 0.2*cm))
                for option in q.options:
                    opt_text = f"<b>{option.label}.</b> {option.text}"
                    story.append(Paragraph(opt_text, styles['MCQOption']))
            
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
            
            # Question number
            q_num = f"Q{section.question_no}" if not variant.variant_label else variant.variant_label
            story.append(Paragraph(
                f"<b>{q_num}.</b> ({q.marks} marks)",
                styles['QuestionText']
            ))
            
            # MCQ answer
            if q.question_type == "mcq":
                answer_text = f"<b>Answer: {q.answer_key}</b>"
                if q.options:
                    correct_option = next((opt for opt in q.options if opt.label == q.answer_key), None)
                    if correct_option:
                        answer_text += f" - {correct_option.text}"
                story.append(Paragraph(answer_text, styles['AnswerText']))
            
            # Descriptive answer
            else:
                if q.answer_key:
                    story.append(Paragraph("<b>Model Answer:</b>", styles['Normal']))
                    story.append(Spacer(1, 0.1*cm))
                    story.append(Paragraph(q.answer_key, styles['AnswerText']))
                
                # Marking scheme
                if q.marking_scheme:
                    story.append(Spacer(1, 0.2*cm))
                    story.append(Paragraph("<b>Marking Scheme:</b>", styles['Normal']))
                    story.append(Spacer(1, 0.1*cm))
                    
                    for point in q.marking_scheme:
                        scheme_text = f"• {point.point} - <b>{point.marks} mark(s)</b>"
                        story.append(Paragraph(scheme_text, styles['AnswerText']))
            
            story.append(Spacer(1, 0.4*cm))
    
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
    for section in paper.sections:
        # Handle OR questions (multiple variants) vs single questions
        if len(section.variants) > 1:
            # OR question - show all variants
            story.append(Paragraph(f"<b>Q{section.question_no}. (OR Question - any variant)</b>", styles['QuestionText']))
            story.append(Spacer(1, 0.2*cm))
            
            for variant in section.variants:
                q = variant.question
                q_type = "MCQ" if q.question_type == "mcq" else "Descriptive"
                
                story.append(Paragraph(
                    f"<b>{variant.variant_label}.</b> ({q_type}, {section.marks} marks, Bloom: {section.bloom_level.title()})",
                    styles['AnswerText']
                ))
                
                # MCQ marking
                if q.question_type == "mcq":
                    story.append(Paragraph(
                        f"Correct answer: <b>{q.answer_key}</b> ({section.marks} marks for correct, 0 for incorrect)",
                        styles['AnswerText']
                    ))
                
                # Descriptive marking scheme
                else:
                    if q.marking_scheme:
                        story.append(Spacer(1, 0.1*cm))
                        
                        table_data = [["Marking Point", "Marks"]]
                        for point in q.marking_scheme:
                            table_data.append([point.point, str(point.marks)])
                        
                        total_marks = sum(p.marks for p in q.marking_scheme)
                        table_data.append(["<b>Total</b>", f"<b>{total_marks}</b>"])
                        
                        table = Table(table_data, colWidths=[12*cm, 2*cm])
                        table.setStyle(TableStyle([
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
                        
                        story.append(table)
                
                story.append(Spacer(1, 0.2*cm))
        else:
            # Single question
            variant = section.variants[0]
            q = variant.question
            q_type = "MCQ" if q.question_type == "mcq" else "Descriptive"
            
            story.append(Paragraph(
                f"<b>Q{section.question_no}.</b> ({q_type}, {section.marks} marks, Bloom: {section.bloom_level.title()})",
                styles['QuestionText']
            ))
            
            # MCQ marking
            if q.question_type == "mcq":
                story.append(Paragraph(
                    f"Correct answer: <b>{q.answer_key}</b> ({section.marks} marks for correct, 0 for incorrect)",
                    styles['AnswerText']
                ))
            
            # Descriptive marking scheme
            else:
                if q.marking_scheme:
                    story.append(Spacer(1, 0.1*cm))
                    
                    table_data = [["Marking Point", "Marks"]]
                    for point in q.marking_scheme:
                        table_data.append([point.point, str(point.marks)])
                    
                    total_marks = sum(p.marks for p in q.marking_scheme)
                    table_data.append(["<b>Total</b>", f"<b>{total_marks}</b>"])
                    
                    table = Table(table_data, colWidths=[12*cm, 2*cm])
                    table.setStyle(TableStyle([
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
                    
                    story.append(table)
        
        story.append(Spacer(1, 0.4*cm))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer
