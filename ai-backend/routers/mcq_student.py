"""
MCQ Student router.
Student-facing endpoints for viewing assigned exams, taking exams,
auto-saving answers (Redis), submitting, and viewing results.
"""

import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import Optional

from database.database import get_db
from database.models import (
    McqExam, McqExamQuestion, McqExamAssignment, McqPoolQuestion,
    McqStudentExamInstance, McqStudentResponse, Student,
)
from database.redis_client import save_answer, get_all_answers, clear_answers
from routers.auth_student import get_current_student

router = APIRouter(prefix="/student/exams", tags=["mcq-student"])


# ─── Schemas ───────────────────────────────────────────────────────────────────

class SaveAnswerRequest(BaseModel):
    question_id: int  # pool_question_id
    selected_option: str  # A, B, C, D


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _check_auto_submit(instance: McqStudentExamInstance, exam: McqExam, db: Session):
    """Auto-submit if time is up and not yet submitted."""
    if instance.submitted_at is not None:
        return  # already submitted

    now = _now()
    # Check if exam end time passed OR if student's personal time is up
    student_end = instance.started_at.replace(tzinfo=timezone.utc) if instance.started_at.tzinfo is None else instance.started_at
    from datetime import timedelta
    personal_end = student_end + timedelta(minutes=exam.duration_minutes)
    exam_end = exam.end_time.replace(tzinfo=timezone.utc) if exam.end_time.tzinfo is None else exam.end_time
    deadline = min(personal_end, exam_end)

    if now >= deadline:
        _do_submit(instance, exam, db, is_auto=True)


def _do_submit(instance: McqStudentExamInstance, exam: McqExam, db: Session, is_auto: bool = False):
    """Flush Redis answers to DB, compute score, mark submitted."""
    # Get any answers from Redis
    redis_answers = get_all_answers(exam.id, instance.student_id)

    # Merge Redis answers into DB responses
    for qid_str, option in redis_answers.items():
        qid = int(qid_str)
        existing = (
            db.query(McqStudentResponse)
            .filter(McqStudentResponse.instance_id == instance.id, McqStudentResponse.pool_question_id == qid)
            .first()
        )
        if existing:
            existing.selected_option = option
        else:
            resp = McqStudentResponse(
                instance_id=instance.id,
                pool_question_id=qid,
                selected_option=option,
            )
            db.add(resp)

    db.flush()

    # Compute score
    responses = (
        db.query(McqStudentResponse)
        .filter(McqStudentResponse.instance_id == instance.id)
        .all()
    )
    answer_map = {r.pool_question_id: r.selected_option for r in responses}

    # Get correct answers for this exam's questions
    question_ids = instance.questions_order
    correct_answers = {}
    for q in db.query(McqPoolQuestion).filter(McqPoolQuestion.id.in_(question_ids)).all():
        correct_answers[q.id] = q.correct_answer

    score = 0
    for qid in question_ids:
        student_ans = answer_map.get(qid)
        correct_ans = correct_answers.get(qid)
        if student_ans and correct_ans and student_ans.upper() == correct_ans.upper():
            score += 1

    instance.score = score
    instance.submitted_at = _now()
    instance.is_auto_submitted = is_auto
    db.commit()

    # Clean up Redis
    clear_answers(exam.id, instance.student_id)


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.get("/")
def list_assigned_exams(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    """List all exams assigned to this student (matched by dept+year+division)."""
    assignments = (
        db.query(McqExamAssignment)
        .filter(
            McqExamAssignment.department_id == student.department_id,
            McqExamAssignment.year_id == student.year_id,
            McqExamAssignment.division_id == student.division_id,
        )
        .all()
    )
    exam_ids = list(set(a.exam_id for a in assignments))
    if not exam_ids:
        return []

    exams = (
        db.query(McqExam)
        .options(joinedload(McqExam.subject))
        .filter(McqExam.id.in_(exam_ids), McqExam.is_active == True)
        .order_by(McqExam.start_time.desc())
        .all()
    )

    # Check if student has an instance for each exam
    instances = (
        db.query(McqStudentExamInstance)
        .filter(McqStudentExamInstance.student_id == student.id, McqStudentExamInstance.exam_id.in_(exam_ids))
        .all()
    )
    instance_map = {inst.exam_id: inst for inst in instances}

    now = _now()
    result = []
    for exam in exams:
        inst = instance_map.get(exam.id)
        exam_end = exam.end_time.replace(tzinfo=timezone.utc) if exam.end_time.tzinfo is None else exam.end_time
        exam_start = exam.start_time.replace(tzinfo=timezone.utc) if exam.start_time.tzinfo is None else exam.start_time

        if inst and inst.submitted_at:
            exam_status = "completed"
        else:
            # Auto-submit check for expired instances
            if inst and not inst.submitted_at:
                _check_auto_submit(inst, exam, db)
                if inst.submitted_at:
                    exam_status = "completed"
                elif now < exam_start:
                    exam_status = "upcoming"
                elif now > exam_end:
                    exam_status = "expired"
                else:
                    exam_status = "in_progress"
            elif now < exam_start:
                exam_status = "upcoming"
            elif now > exam_end:
                exam_status = "expired"
            else:
                exam_status = "available"

        result.append({
            "id": exam.id,
            "title": exam.title,
            "subject_name": exam.subject.name if exam.subject else None,
            "exam_mode": exam.exam_mode,
            "start_time": exam.start_time.isoformat(),
            "end_time": exam.end_time.isoformat(),
            "duration_minutes": exam.duration_minutes,
            "total_questions": exam.total_questions,
            "status": exam_status,
            "score": inst.score if inst and inst.submitted_at else None,
            "show_result_to_student": exam.show_result_to_student,
        })

    return result


@router.post("/{exam_id}/start")
def start_exam(exam_id: int, student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    """Start an exam. Creates a student exam instance with assigned questions."""
    exam = (
        db.query(McqExam)
        .options(joinedload(McqExam.questions).joinedload(McqExamQuestion.pool_question))
        .filter(McqExam.id == exam_id, McqExam.is_active == True)
        .first()
    )
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    # Check time window
    now = _now()
    exam_start = exam.start_time.replace(tzinfo=timezone.utc) if exam.start_time.tzinfo is None else exam.start_time
    exam_end = exam.end_time.replace(tzinfo=timezone.utc) if exam.end_time.tzinfo is None else exam.end_time

    if now < exam_start:
        raise HTTPException(status_code=400, detail="Exam has not started yet")
    if now > exam_end:
        raise HTTPException(status_code=400, detail="Exam has ended")

    # Check assignment
    has_assignment = (
        db.query(McqExamAssignment)
        .filter(
            McqExamAssignment.exam_id == exam_id,
            McqExamAssignment.department_id == student.department_id,
            McqExamAssignment.year_id == student.year_id,
            McqExamAssignment.division_id == student.division_id,
        )
        .first()
    )
    if not has_assignment:
        raise HTTPException(status_code=403, detail="This exam is not assigned to you")

    # Check if already started
    existing = (
        db.query(McqStudentExamInstance)
        .filter(McqStudentExamInstance.exam_id == exam_id, McqStudentExamInstance.student_id == student.id)
        .first()
    )
    if existing:
        # Auto-submit check
        _check_auto_submit(existing, exam, db)
        if existing.submitted_at:
            raise HTTPException(status_code=400, detail="Exam already submitted")

        # Return existing instance
        return _instance_response(existing, exam, db)

    # Build question list
    all_pool_ids = [eq.pool_question_id for eq in sorted(exam.questions, key=lambda x: x.question_order)]

    if exam.exam_mode == "dynamic":
        # Random subset
        selected = random.sample(all_pool_ids, min(exam.total_questions, len(all_pool_ids)))
        random.shuffle(selected)
    else:
        selected = all_pool_ids

    instance = McqStudentExamInstance(
        exam_id=exam_id,
        student_id=student.id,
        questions_order=selected,
        total_questions=len(selected),
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)

    return _instance_response(instance, exam, db)


def _instance_response(instance: McqStudentExamInstance, exam: McqExam, db: Session) -> dict:
    """Build the response for an exam instance (with questions but without correct answers)."""
    pool_qs = (
        db.query(McqPoolQuestion)
        .filter(McqPoolQuestion.id.in_(instance.questions_order))
        .all()
    )
    pq_map = {q.id: q for q in pool_qs}

    # Get existing responses
    responses = (
        db.query(McqStudentResponse)
        .filter(McqStudentResponse.instance_id == instance.id)
        .all()
    )
    response_map = {r.pool_question_id: r.selected_option for r in responses}

    # Also get Redis answers
    redis_answers = get_all_answers(exam.id, instance.student_id)

    questions = []
    for idx, qid in enumerate(instance.questions_order):
        pq = pq_map.get(qid)
        if not pq:
            continue
        # Prefer Redis answer over DB answer
        saved = redis_answers.get(str(qid)) or response_map.get(qid)
        questions.append({
            "question_number": idx + 1,
            "pool_question_id": qid,
            "question_text": pq.question_text,
            "options": pq.options,
            "saved_answer": saved,
        })

    from datetime import timedelta
    student_start = instance.started_at.replace(tzinfo=timezone.utc) if instance.started_at.tzinfo is None else instance.started_at
    personal_end = student_start + timedelta(minutes=exam.duration_minutes)
    exam_end = exam.end_time.replace(tzinfo=timezone.utc) if exam.end_time.tzinfo is None else exam.end_time
    deadline = min(personal_end, exam_end)

    return {
        "instance_id": instance.id,
        "exam_id": exam.id,
        "exam_title": exam.title,
        "total_questions": instance.total_questions,
        "duration_minutes": exam.duration_minutes,
        "started_at": instance.started_at.isoformat(),
        "deadline": deadline.isoformat(),
        "remaining_seconds": max(0, int((deadline - _now()).total_seconds())),
        "questions": questions,
    }


@router.post("/{exam_id}/save-answer")
def save_exam_answer(
    exam_id: int,
    request: SaveAnswerRequest,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Auto-save a single answer to Redis."""
    instance = (
        db.query(McqStudentExamInstance)
        .filter(McqStudentExamInstance.exam_id == exam_id, McqStudentExamInstance.student_id == student.id)
        .first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Exam not started")
    if instance.submitted_at:
        raise HTTPException(status_code=400, detail="Exam already submitted")

    exam = db.query(McqExam).filter(McqExam.id == exam_id).first()

    # Check time
    _check_auto_submit(instance, exam, db)
    if instance.submitted_at:
        raise HTTPException(status_code=400, detail="Exam time expired — auto-submitted")

    # Validate question belongs to this instance
    if request.question_id not in instance.questions_order:
        raise HTTPException(status_code=400, detail="Question not in this exam")

    # Save to Redis with TTL
    ttl_minutes = exam.duration_minutes + 30
    save_answer(exam_id, student.id, request.question_id, request.selected_option, ttl_minutes)

    return {"status": "saved", "question_id": request.question_id, "selected_option": request.selected_option}


@router.post("/{exam_id}/submit")
def submit_exam(
    exam_id: int,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Final submit: flush Redis → DB, compute score, mark submitted."""
    instance = (
        db.query(McqStudentExamInstance)
        .filter(McqStudentExamInstance.exam_id == exam_id, McqStudentExamInstance.student_id == student.id)
        .first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Exam not started")
    if instance.submitted_at:
        raise HTTPException(status_code=400, detail="Exam already submitted")

    exam = db.query(McqExam).filter(McqExam.id == exam_id).first()
    _do_submit(instance, exam, db, is_auto=False)

    return {
        "status": "submitted",
        "score": instance.score,
        "total_questions": instance.total_questions,
        "percentage": round((instance.score / instance.total_questions) * 100, 1) if instance.total_questions > 0 else 0,
    }


@router.get("/{exam_id}/result")
def get_exam_result(
    exam_id: int,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """View result (only if show_result_to_student is True)."""
    exam = db.query(McqExam).filter(McqExam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    instance = (
        db.query(McqStudentExamInstance)
        .filter(McqStudentExamInstance.exam_id == exam_id, McqStudentExamInstance.student_id == student.id)
        .first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="You have not taken this exam")
    if not instance.submitted_at:
        raise HTTPException(status_code=400, detail="Exam not yet submitted")

    result = {
        "exam_id": exam_id,
        "exam_title": exam.title,
        "score": instance.score,
        "total_questions": instance.total_questions,
        "percentage": round((instance.score / instance.total_questions) * 100, 1) if instance.total_questions > 0 else 0,
        "submitted_at": instance.submitted_at.isoformat(),
        "is_auto_submitted": instance.is_auto_submitted,
        "show_result_to_student": exam.show_result_to_student,
    }

    if exam.show_result_to_student:
        # Include detailed question-by-question breakdown
        responses = (
            db.query(McqStudentResponse)
            .options(joinedload(McqStudentResponse.pool_question))
            .filter(McqStudentResponse.instance_id == instance.id)
            .all()
        )
        response_map = {r.pool_question_id: r for r in responses}

        pool_qs = db.query(McqPoolQuestion).filter(McqPoolQuestion.id.in_(instance.questions_order)).all()
        pq_map = {q.id: q for q in pool_qs}

        breakdown = []
        for idx, qid in enumerate(instance.questions_order):
            pq = pq_map.get(qid)
            resp = response_map.get(qid)
            if pq:
                is_correct = resp and resp.selected_option and resp.selected_option.upper() == pq.correct_answer.upper()
                breakdown.append({
                    "question_number": idx + 1,
                    "question_text": pq.question_text,
                    "options": pq.options,
                    "correct_answer": pq.correct_answer,
                    "your_answer": resp.selected_option if resp else None,
                    "is_correct": is_correct,
                    "explanation": pq.explanation,
                })

        result["breakdown"] = breakdown

    return result
