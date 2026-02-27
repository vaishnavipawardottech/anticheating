"""
MCQ Question Pool router.
Teachers can generate MCQs via AI or add manually. Pool questions are tagged with
subject, unit, bloom's level, and difficulty for filtering.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
import json

from database.database import get_db
from database.models import McqPoolQuestion, Subject, Unit, Teacher
from routers.auth_teacher import get_current_teacher

router = APIRouter(prefix="/mcq-pool", tags=["mcq-pool"])


# ─── Schemas ───────────────────────────────────────────────────────────────────

class OptionSchema(BaseModel):
    label: str = Field(..., description="Option label (A, B, C, D)")
    text: str = Field(..., description="Option text")

class McqPoolCreateRequest(BaseModel):
    subject_id: int
    unit_id: Optional[int] = None
    question_text: str
    options: List[OptionSchema]
    correct_answer: str = Field(..., description="Correct option label (A, B, C, D)")
    explanation: Optional[str] = None
    blooms_level: Optional[str] = None
    difficulty: Optional[str] = None

class McqPoolUpdateRequest(BaseModel):
    question_text: Optional[str] = None
    options: Optional[List[OptionSchema]] = None
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None
    blooms_level: Optional[str] = None
    difficulty: Optional[str] = None
    unit_id: Optional[int] = None

class McqPoolGenerateRequest(BaseModel):
    subject_id: int
    unit_ids: List[int] = Field(..., description="Units to generate MCQs from")
    count: int = Field(10, ge=1, le=50, description="Number of MCQs to generate per unit")
    difficulty: Optional[str] = Field(None, description="Target difficulty: easy, medium, hard")
    blooms_level: Optional[str] = Field(None, description="Target bloom's level")

class McqBulkCreateRequest(BaseModel):
    questions: List[McqPoolCreateRequest]


def _question_dict(q: McqPoolQuestion) -> dict:
    return {
        "id": q.id,
        "subject_id": q.subject_id,
        "unit_id": q.unit_id,
        "question_text": q.question_text,
        "options": q.options,
        "correct_answer": q.correct_answer,
        "explanation": q.explanation,
        "blooms_level": q.blooms_level,
        "difficulty": q.difficulty,
        "created_by": q.created_by,
        "created_at": q.created_at.isoformat() if q.created_at else None,
        "unit_name": q.unit.name if q.unit else None,
        "subject_name": q.subject.name if q.subject else None,
    }


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.get("/")
def list_pool_questions(
    subject_id: Optional[int] = None,
    unit_id: Optional[int] = None,
    blooms_level: Optional[str] = None,
    difficulty: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """List MCQ pool questions with optional filters."""
    q = db.query(McqPoolQuestion)
    if subject_id:
        q = q.filter(McqPoolQuestion.subject_id == subject_id)
    if unit_id:
        q = q.filter(McqPoolQuestion.unit_id == unit_id)
    if blooms_level:
        q = q.filter(McqPoolQuestion.blooms_level == blooms_level)
    if difficulty:
        q = q.filter(McqPoolQuestion.difficulty == difficulty)

    total = q.count()
    questions = q.order_by(McqPoolQuestion.id.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "questions": [_question_dict(qn) for qn in questions],
    }


@router.get("/{question_id}")
def get_pool_question(question_id: int, teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Get a single pool question."""
    q = db.query(McqPoolQuestion).filter(McqPoolQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    return _question_dict(q)


@router.post("/manual", status_code=201)
def create_pool_question(request: McqPoolCreateRequest, teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Manually add a question to the pool."""
    # Validate subject
    subject = db.query(Subject).filter(Subject.id == request.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    if request.unit_id:
        unit = db.query(Unit).filter(Unit.id == request.unit_id, Unit.subject_id == request.subject_id).first()
        if not unit:
            raise HTTPException(status_code=404, detail="Unit not found or doesn't belong to this subject")

    q = McqPoolQuestion(
        subject_id=request.subject_id,
        unit_id=request.unit_id,
        question_text=request.question_text,
        options=[opt.model_dump() for opt in request.options],
        correct_answer=request.correct_answer,
        explanation=request.explanation,
        blooms_level=request.blooms_level,
        difficulty=request.difficulty,
        created_by=teacher.id,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _question_dict(q)


@router.post("/bulk", status_code=201)
def bulk_create_pool_questions(request: McqBulkCreateRequest, teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Bulk add questions to the pool."""
    created = []
    for item in request.questions:
        q = McqPoolQuestion(
            subject_id=item.subject_id,
            unit_id=item.unit_id,
            question_text=item.question_text,
            options=[opt.model_dump() for opt in item.options],
            correct_answer=item.correct_answer,
            explanation=item.explanation,
            blooms_level=item.blooms_level,
            difficulty=item.difficulty,
            created_by=teacher.id,
        )
        db.add(q)
        created.append(q)
    db.commit()
    for q in created:
        db.refresh(q)
    return {"created": len(created), "questions": [_question_dict(q) for q in created]}


@router.put("/{question_id}")
def update_pool_question(question_id: int, request: McqPoolUpdateRequest, teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Update a pool question."""
    q = db.query(McqPoolQuestion).filter(McqPoolQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    if request.question_text is not None:
        q.question_text = request.question_text
    if request.options is not None:
        q.options = [opt.model_dump() for opt in request.options]
    if request.correct_answer is not None:
        q.correct_answer = request.correct_answer
    if request.explanation is not None:
        q.explanation = request.explanation
    if request.blooms_level is not None:
        q.blooms_level = request.blooms_level
    if request.difficulty is not None:
        q.difficulty = request.difficulty
    if request.unit_id is not None:
        q.unit_id = request.unit_id

    db.commit()
    db.refresh(q)
    return _question_dict(q)


@router.delete("/{question_id}", status_code=204)
def delete_pool_question(question_id: int, teacher: Teacher = Depends(get_current_teacher), db: Session = Depends(get_db)):
    """Delete a pool question."""
    q = db.query(McqPoolQuestion).filter(McqPoolQuestion.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(q)
    db.commit()


@router.post("/generate", status_code=201)
async def generate_pool_questions(
    request: McqPoolGenerateRequest,
    teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    AI-generate MCQ questions from ingested documents for the specified units.
    Uses the existing retrieval + LLM generation pipeline.
    """
    import openai
    import os
    from routers.context import build_context_impl

    subject = db.query(Subject).filter(Subject.id == request.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    units = db.query(Unit).filter(Unit.id.in_(request.unit_ids), Unit.subject_id == request.subject_id).all()
    if not units:
        raise HTTPException(status_code=404, detail="No valid units found for this subject")

    all_generated = []

    for unit in units:
        # Build context from ingested docs for this unit
        try:
            context_resp = await build_context_impl(
                subject_id=request.subject_id,
                db=db,
                unit_id=unit.id,
                top_k=20,
                max_tokens=6000,
            )
        except Exception:
            context_resp = None

        if not context_resp or not context_resp.context_text.strip():
            continue

        # Prepare the LLM prompt
        difficulty_hint = f"Target difficulty: {request.difficulty}. " if request.difficulty else ""
        blooms_hint = f"Target Bloom's level: {request.blooms_level}. " if request.blooms_level else ""

        prompt = f"""You are an expert exam question generator. Generate exactly {request.count} multiple-choice questions (MCQs) based on the following educational content.

Subject: {subject.name}
Unit: {unit.name}
{difficulty_hint}{blooms_hint}

CONTENT:
{context_resp.context_text}

For each question, provide:
1. question_text: Clear, unambiguous question
2. options: Exactly 4 options labeled A, B, C, D
3. correct_answer: The correct option label (A, B, C, or D)
4. explanation: Brief explanation of why the answer is correct
5. blooms_level: One of: remember, understand, apply, analyze, evaluate, create
6. difficulty: One of: easy, medium, hard

Return ONLY a JSON array of objects with these fields. Each option should be an object with "label" and "text" fields.

Example format:
[
  {{
    "question_text": "What is X?",
    "options": [{{"label": "A", "text": "Option 1"}}, {{"label": "B", "text": "Option 2"}}, {{"label": "C", "text": "Option 3"}}, {{"label": "D", "text": "Option 4"}}],
    "correct_answer": "A",
    "explanation": "Because...",
    "blooms_level": "remember",
    "difficulty": "easy"
  }}
]"""

        try:
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            parsed = json.loads(content)

            # Handle both {"questions": [...]} and direct [...] format
            if isinstance(parsed, dict):
                questions_list = parsed.get("questions", parsed.get("mcqs", []))
            elif isinstance(parsed, list):
                questions_list = parsed
            else:
                questions_list = []

            for item in questions_list:
                q = McqPoolQuestion(
                    subject_id=request.subject_id,
                    unit_id=unit.id,
                    question_text=item.get("question_text", ""),
                    options=item.get("options", []),
                    correct_answer=item.get("correct_answer", "A"),
                    explanation=item.get("explanation"),
                    blooms_level=item.get("blooms_level", request.blooms_level),
                    difficulty=item.get("difficulty", request.difficulty),
                    created_by=teacher.id,
                )
                db.add(q)
                all_generated.append(q)
        except Exception as e:
            # Log but don't fail entirely — continue with other units
            print(f"Error generating MCQs for unit {unit.name}: {e}")
            continue

    db.commit()
    for q in all_generated:
        db.refresh(q)

    return {
        "generated": len(all_generated),
        "questions": [_question_dict(q) for q in all_generated],
    }
