"""
Exam Preview Formatter — generation/exam_preview_formatter.py

Converts parsed GenerationSpec (MCQSpec or SubjectiveSpec) into a 
structured preview that teachers can review before generation.

Similar to TOC normalization for documents — shows EXACTLY what will be generated
in a clear, hierarchical format.
"""

from typing import List, Dict
from sqlalchemy.orm import Session

from database.models import Subject, Unit
from generation.schemas import (
    MCQSpec,
    SubjectiveSpec,
    ExamStructurePreview,
    ExamQuestionPreview,
    ExamSectionPreview,
)


def format_mcq_preview(
    spec: MCQSpec,
    subject_id: int,
    request_text: str,
    db: Session,
) -> ExamStructurePreview:
    """
    Format MCQ spec as structured preview.
    
    Example output:
    ```
    MCQ Examination
    Total: 20 questions, 40 marks
    
    Unit 1: Introduction to OS (5 questions, 10 marks)
    Unit 2: Process Management (10 questions, 20 marks)
    Unit 3: Memory Management (5 questions, 10 marks)
    ```
    """
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    subject_name = subject.name if subject else f"Subject {subject_id}"
    
    # Get unit names
    unit_map = {
        u.id: u.name
        for u in db.query(Unit).filter(Unit.subject_id == subject_id).all()
    }
    
    # Build question-by-question preview
    mcq_preview: List[ExamQuestionPreview] = []
    question_no = 1
    
    for dist in spec.unit_distribution:
        unit_name = unit_map.get(dist.unit_id, f"Unit {dist.unit_id}")
        marks_for_unit = dist.count * spec.marks_per_question
        
        for i in range(dist.count):
            mcq_preview.append(
                ExamQuestionPreview(
                    question_no=question_no,
                    unit_id=dist.unit_id,
                    unit_name=unit_name,
                    question_type="mcq",
                    marks=spec.marks_per_question,
                    description=f"MCQ from {unit_name}",
                )
            )
            question_no += 1
    
    return ExamStructurePreview(
        subject_id=subject_id,
        subject_name=subject_name,
        request_text=request_text,
        exam_type="MCQ Examination",
        total_marks=spec.total_marks,
        total_questions=spec.total_questions,
        difficulty=spec.difficulty,
        mcq_preview=mcq_preview,
        marks_per_question=spec.marks_per_question,
        sections=None,
        parsed_spec=spec.model_dump(),
    )


def format_subjective_preview(
    spec: SubjectiveSpec,
    subject_id: int,
    request_text: str,
    db: Session,
) -> ExamStructurePreview:
    """
    Format Subjective spec as structured preview.
    
    Example output:
    ```
    Subjective Examination
    Total: 30 marks
    
    Section A - Unit 1: Operating Systems
      4 questions, attempt any 2, 5 marks each → 10 marks
      
    Section B - Unit 2: Process Management  
      4 questions, attempt any 2, 5 marks each → 10 marks
      
    Section C - Unit 3: Memory Management
      4 questions, attempt any 2, 5 marks each → 10 marks
    ```
    """
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    subject_name = subject.name if subject else f"Subject {subject_id}"
    
    # Get unit names
    unit_map = {
        u.id: u.name
        for u in db.query(Unit).filter(Unit.subject_id == subject_id).all()
    }
    
    # Build section-by-section preview
    sections: List[ExamSectionPreview] = []
    section_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    total_questions = 0
    
    for idx, section in enumerate(spec.sections):
        unit_name = unit_map.get(section.unit_id, f"Unit {section.unit_id}")
        section_letter = section_letters[idx] if idx < len(section_letters) else str(idx + 1)
        
        # Build note
        if section.attempt < section.sub_questions:
            note = f"Attempt any {section.attempt} out of {section.sub_questions}"
        else:
            note = "All questions compulsory"
        
        sections.append(
            ExamSectionPreview(
                section_no=idx + 1,
                title=f"Section {section_letter} - {unit_name}",
                unit_id=section.unit_id,
                unit_name=unit_name,
                total_questions=section.sub_questions,
                attempt_required=section.attempt,
                marks_per_question=section.marks_per_sub,
                section_marks=section.section_marks,
                question_type=section.question_type,
                note=note,
            )
        )
        total_questions += section.sub_questions
    
    return ExamStructurePreview(
        subject_id=subject_id,
        subject_name=subject_name,
        request_text=request_text,
        exam_type="Subjective Examination",
        total_marks=spec.total_marks,
        total_questions=total_questions,
        difficulty=spec.difficulty,
        mcq_preview=None,
        marks_per_question=None,
        sections=sections,
        parsed_spec=spec.model_dump(),
    )


def format_exam_preview(
    spec: MCQSpec | SubjectiveSpec,
    subject_id: int,
    request_text: str,
    db: Session,
) -> ExamStructurePreview:
    """
    Main entry point: format any spec type as exam structure preview.
    """
    if isinstance(spec, MCQSpec):
        return format_mcq_preview(spec, subject_id, request_text, db)
    else:
        return format_subjective_preview(spec, subject_id, request_text, db)
