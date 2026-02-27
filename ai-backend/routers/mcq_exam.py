"""
MCQ Exam management router (teacher-facing).
Create exams (static/dynamic), assign to students by dept/year/division,
view results, toggle result visibility.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from database.database import get_db
from database.models import (
    McqExam, McqExamQuestion, McqExamAssignment, McqPoolQuestion,
    McqStudentExamInstance, McqStudentResponse, ProctoringEvent,
    Subject, Unit, Teacher, Department, Division, YearOfStudy, Student,
)
from routers.auth_teacher import get_current_teacher

router = APIRouter(prefix="/mcq-exams", tags=["mcq-exams"])


# ─── Schemas ───────────────────────────────────────────────────────────────────

class ExamAssignItem(BaseModel):
    department_id: int
    year_id: int
    division_id: int

class ExamCreateRequest(BaseModel):
    title: str
    subject_id: int
    exam_mode: str = Field("static", description="'static' or 'dynamic'")
    start_time: datetime
    end_time: datetime
    duration_minutes: int = Field(..., ge=1, le=600)
    total_questions: int = Field(..., ge=1, le=200)
    question_ids: List[int] = Field(..., description="Pool question IDs to include")
    show_result_to_student: bool = False
    assignments: Optional[List[ExamAssignItem]] = None

class ExamUpdateRequest(BaseModel):
    title: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    show_result_to_student: Optional[bool] = None

class ExamAssignRequest(BaseModel):
    department_id: int
    year_id: int
    division_id: int


def _exam_summary(exam: McqExam) -> dict:
    return {
        "id": exam.id,
        "title": exam.title,
        "subject_id": exam.subject_id,
        "subject_name": exam.subject.name if exam.subject else None,
        "exam_mode": exam.exam_mode,
        "start_time": exam.start_time.isoformat() if exam.start_time else None,
        "end_time": exam.end_time.isoformat() if exam.end_time else None,
        "duration_minutes": exam.duration_minutes,
        "total_questions": exam.total_questions,
        "show_result_to_student": exam.show_result_to_student,
        "is_active": exam.is_active,
        "created_at": exam.created_at.isoformat() if exam.created_at else None,
        "question_count": len(exam.questions) if exam.questions else 0,
        "assignment_count": len(exam.assignments) if exam.assignments else 0,
    }


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
def create_exam(
    request: ExamCreateRequest,
    teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Create a new MCQ exam. Teacher selects questions from pool."""
    subject = db.query(Subject).filter(Subject.id == request.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    if request.exam_mode not in ("static", "dynamic"):
        raise HTTPException(status_code=400, detail="exam_mode must be 'static' or 'dynamic'")

    if request.start_time >= request.end_time:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    # Validate question IDs exist
    pool_qs = db.query(McqPoolQuestion).filter(McqPoolQuestion.id.in_(request.question_ids)).all()
    if len(pool_qs) != len(request.question_ids):
        raise HTTPException(status_code=400, detail="Some question IDs are invalid")

    # For static mode, total_questions should match question count
    if request.exam_mode == "static":
        total_q = len(request.question_ids)
    else:
        # Dynamic: total_questions must be <= available questions
        if request.total_questions > len(request.question_ids):
            raise HTTPException(status_code=400, detail="total_questions exceeds available pool questions")
        total_q = request.total_questions

    exam = McqExam(
        title=request.title,
        subject_id=request.subject_id,
        created_by=teacher.id,
        exam_mode=request.exam_mode,
        start_time=request.start_time,
        end_time=request.end_time,
        duration_minutes=request.duration_minutes,
        total_questions=total_q,
        show_result_to_student=request.show_result_to_student,
    )
    db.add(exam)
    db.flush()

    # Add questions
    for idx, qid in enumerate(request.question_ids):
        eq = McqExamQuestion(exam_id=exam.id, pool_question_id=qid, question_order=idx + 1)
        db.add(eq)

    # Add assignments if provided
    if request.assignments:
        for assign in request.assignments:
            # Check for duplicates
            existing = (
                db.query(McqExamAssignment)
                .filter(
                    McqExamAssignment.exam_id == exam.id,
                    McqExamAssignment.department_id == assign.department_id,
                    McqExamAssignment.year_id == assign.year_id,
                    McqExamAssignment.division_id == assign.division_id,
                )
                .first()
            )
            if not existing:
                assignment = McqExamAssignment(
                    exam_id=exam.id,
                    department_id=assign.department_id,
                    year_id=assign.year_id,
                    division_id=assign.division_id,
                )
                db.add(assignment)

    db.commit()
    db.refresh(exam)

    return _exam_summary(exam)


@router.get("/")
def list_exams(
    teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """List all exams created by the current teacher."""
    exams = (
        db.query(McqExam)
        .options(joinedload(McqExam.subject), joinedload(McqExam.questions), joinedload(McqExam.assignments))
        .filter(McqExam.created_by == teacher.id)
        .order_by(McqExam.created_at.desc())
        .all()
    )
    return [_exam_summary(e) for e in exams]


@router.get("/{exam_id}")
def get_exam(exam_id: int, teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Get exam details including questions and assignments."""
    exam = (
        db.query(McqExam)
        .options(
            joinedload(McqExam.subject),
            joinedload(McqExam.questions).joinedload(McqExamQuestion.pool_question),
            joinedload(McqExam.assignments).joinedload(McqExamAssignment.department),
            joinedload(McqExam.assignments).joinedload(McqExamAssignment.year_of_study),
            joinedload(McqExam.assignments).joinedload(McqExamAssignment.division),
        )
        .filter(McqExam.id == exam_id, McqExam.created_by == teacher.id)
        .first()
    )
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    # Get submission stats
    submissions = db.query(McqStudentExamInstance).filter(McqStudentExamInstance.exam_id == exam_id).all()

    return {
        **_exam_summary(exam),
        "questions": [
            {
                "id": eq.id,
                "pool_question_id": eq.pool_question_id,
                "question_order": eq.question_order,
                "question_text": eq.pool_question.question_text if eq.pool_question else None,
                "options": eq.pool_question.options if eq.pool_question else None,
                "correct_answer": eq.pool_question.correct_answer if eq.pool_question else None,
                "blooms_level": eq.pool_question.blooms_level if eq.pool_question else None,
                "difficulty": eq.pool_question.difficulty if eq.pool_question else None,
            }
            for eq in sorted(exam.questions, key=lambda x: x.question_order)
        ],
        "assignments": [
            {
                "id": a.id,
                "department": {"id": a.department.id, "name": a.department.name} if a.department else None,
                "year_of_study": {"id": a.year_of_study.id, "year": a.year_of_study.year, "label": a.year_of_study.label} if a.year_of_study else None,
                "division": {"id": a.division.id, "name": a.division.name} if a.division else None,
            }
            for a in exam.assignments
        ],
        "submissions": {
            "total": len(submissions),
            "completed": sum(1 for s in submissions if s.submitted_at is not None),
            "in_progress": sum(1 for s in submissions if s.submitted_at is None),
        },
    }


@router.put("/{exam_id}")
def update_exam(exam_id: int, request: ExamUpdateRequest, teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Update exam metadata (only before start time or for show_result)."""
    exam = db.query(McqExam).filter(McqExam.id == exam_id, McqExam.created_by == teacher.id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    if request.title is not None:
        exam.title = request.title
    if request.start_time is not None:
        exam.start_time = request.start_time
    if request.end_time is not None:
        exam.end_time = request.end_time
    if request.duration_minutes is not None:
        exam.duration_minutes = request.duration_minutes
    if request.show_result_to_student is not None:
        exam.show_result_to_student = request.show_result_to_student

    db.commit()
    db.refresh(exam)
    return _exam_summary(exam)


@router.delete("/{exam_id}", status_code=204)
def delete_exam(exam_id: int, teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Delete an exam."""
    exam = db.query(McqExam).filter(McqExam.id == exam_id, McqExam.created_by == teacher.id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    db.delete(exam)
    db.commit()


@router.post("/{exam_id}/assign", status_code=201)
def assign_exam(
    exam_id: int,
    request: ExamAssignRequest,
    teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Assign exam to a dept + year + division combination."""
    exam = db.query(McqExam).filter(McqExam.id == exam_id, McqExam.created_by == teacher.id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    # Check if already assigned to this combination
    existing = (
        db.query(McqExamAssignment)
        .filter(
            McqExamAssignment.exam_id == exam_id,
            McqExamAssignment.department_id == request.department_id,
            McqExamAssignment.year_id == request.year_id,
            McqExamAssignment.division_id == request.division_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Already assigned to this combination")

    assignment = McqExamAssignment(
        exam_id=exam_id,
        department_id=request.department_id,
        year_id=request.year_id,
        division_id=request.division_id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return {
        "id": assignment.id,
        "exam_id": assignment.exam_id,
        "department_id": assignment.department_id,
        "year_id": assignment.year_id,
        "division_id": assignment.division_id,
    }


@router.delete("/{exam_id}/assign/{assignment_id}", status_code=204)
def remove_assignment(
    exam_id: int,
    assignment_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Remove an exam assignment."""
    exam = db.query(McqExam).filter(McqExam.id == exam_id, McqExam.created_by == teacher.id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    assignment = db.query(McqExamAssignment).filter(
        McqExamAssignment.id == assignment_id, McqExamAssignment.exam_id == exam_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    db.delete(assignment)
    db.commit()


@router.patch("/{exam_id}/toggle-results")
def toggle_result_visibility(exam_id: int, teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Toggle show_result_to_student flag."""
    exam = db.query(McqExam).filter(McqExam.id == exam_id, McqExam.created_by == teacher.id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    print(exam.show_result_to_student)
    exam.show_result_to_student = not exam.show_result_to_student
    db.commit()
    return {"show_result_to_student": exam.show_result_to_student}


@router.get("/{exam_id}/results")
def get_exam_results(exam_id: int, teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Get all student results for an exam."""
    exam = db.query(McqExam).filter(McqExam.id == exam_id, McqExam.created_by == teacher.id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    instances = (
        db.query(McqStudentExamInstance)
        .options(joinedload(McqStudentExamInstance.student))
        .filter(
            McqStudentExamInstance.exam_id == exam_id,
            McqStudentExamInstance.submitted_at.isnot(None),
        )
        .order_by(McqStudentExamInstance.score.desc().nullslast())
        .all()
    )

    return {
        "exam_id": exam_id,
        "exam_title": exam.title,
        "total_students": len(instances),
        "results": [
            {
                "student_id": inst.student_id,
                "student_name": inst.student.full_name if inst.student else None,
                "student_email": inst.student.email if inst.student else None,
                "score": inst.score,
                "total_questions": inst.total_questions,
                "percentage": round((inst.score / inst.total_questions) * 100, 1) if inst.score is not None and inst.total_questions > 0 else None,
                "started_at": inst.started_at.isoformat() if inst.started_at else None,
                "submitted_at": inst.submitted_at.isoformat() if inst.submitted_at else None,
                "is_auto_submitted": inst.is_auto_submitted,
            }
            for inst in instances
        ],
    }


@router.get("/student/{student_id}/history")
def get_student_exam_history(
    student_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Get all exam results for a specific student (across teacher's exams)."""
    # Get all exams created by this teacher
    teacher_exam_ids = [
        e.id for e in db.query(McqExam.id).filter(McqExam.created_by == teacher.id).all()
    ]
    if not teacher_exam_ids:
        return {"student_id": student_id, "exams": []}

    instances = (
        db.query(McqStudentExamInstance)
        .options(joinedload(McqStudentExamInstance.exam).joinedload(McqExam.subject))
        .filter(
            McqStudentExamInstance.student_id == student_id,
            McqStudentExamInstance.exam_id.in_(teacher_exam_ids),
        )
        .order_by(McqStudentExamInstance.started_at.desc())
        .all()
    )

    return {
        "student_id": student_id,
        "exams": [
            {
                "exam_id": inst.exam_id,
                "exam_title": inst.exam.title if inst.exam else None,
                "subject_name": inst.exam.subject.name if inst.exam and inst.exam.subject else None,
                "score": inst.score,
                "total_questions": inst.total_questions,
                "percentage": round((inst.score / inst.total_questions) * 100, 1) if inst.score is not None and inst.total_questions > 0 else None,
                "started_at": inst.started_at.isoformat() if inst.started_at else None,
                "submitted_at": inst.submitted_at.isoformat() if inst.submitted_at else None,
                "is_auto_submitted": inst.is_auto_submitted,
            }
            for inst in instances
        ],
    }


@router.get("/{exam_id}/proctoring")
def get_exam_proctoring(
    exam_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Get all proctoring events for an exam, grouped by student."""
    exam = db.query(McqExam).filter(McqExam.id == exam_id, McqExam.created_by == teacher.id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    # Get all instances for this exam
    instances = (
        db.query(McqStudentExamInstance)
        .options(joinedload(McqStudentExamInstance.student))
        .filter(McqStudentExamInstance.exam_id == exam_id)
        .all()
    )

    result = []
    for inst in instances:
        events = (
            db.query(ProctoringEvent)
            .filter(ProctoringEvent.instance_id == inst.id)
            .order_by(ProctoringEvent.created_at.asc())
            .all()
        )
        if not events:
            continue

        result.append({
            "student_id": inst.student_id,
            "student_name": inst.student.full_name if inst.student else None,
            "student_email": inst.student.email if inst.student else None,
            "instance_id": inst.id,
            "event_count": len(events),
            "events": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "details": e.details,
                    "snapshot_url": f"/uploads/{e.snapshot_url}" if e.snapshot_url else None,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ],
        })

    return {
        "exam_id": exam_id,
        "exam_title": exam.title,
        "students_with_events": len(result),
        "students": sorted(result, key=lambda x: x["event_count"], reverse=True),
    }
