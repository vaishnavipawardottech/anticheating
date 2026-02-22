"""
Generation Router — /generation

Orchestrates the complete 9-step paper generation pipeline.
Endpoints:
  POST /generation/generate-paper    — generate a full paper
  GET  /generation/papers            — list papers for a subject
  GET  /generation/papers/{id}       — get full paper JSON
  GET  /generation/co-map/{subject_id} — unit→CO mapping for frontend
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel, EmailStr

from database.database import get_db
from database.models import GeneratedPaper, Subject, Unit, PaperType, VisualChunk, Teacher, PaperShare
from routers.auth import get_current_teacher
from generation.schemas import (
    PaperOutput, PaperSummary, GeneratePaperResponse, PatternInput, QuestionSpec,
    NLGenerateRequest, ParsedSpecResponse, MCQSpec, SubjectiveSpec,
    ExamStructurePreview, ApproveAndGenerateRequest,
)
from generation.pattern_interpreter import interpret_pattern, interpret_pattern_from_pdf
from generation.blueprint_builder import build_blueprint
from generation.retrieval_engine import (
    retrieve_chunks_for_spec,
    retrieve_visual_chunks_for_spec,
    get_table_markdown_for_chunks,
)
from generation.question_generator import generate_question
from generation.co_mapper import map_co, get_co_map_for_subject
from generation.paper_assembler import assemble_paper
from generation.validator import validate_paper
from generation.usage_tracker import increment_usage, collect_used_chunk_ids
from generation.nl_interpreter import interpret_nl_request
from generation.exam_preview_formatter import format_exam_preview

router = APIRouter(prefix="/generation", tags=["generation"])

# Use Python's standard logger so output appears in the uvicorn console
log = logging.getLogger("generation.pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")


# ─── NL Parse (dry-run / test) ─────────────────────────────────────────────────

@router.post("/parse", response_model=ParsedSpecResponse)
async def parse_nl_request(
    request: NLGenerateRequest,
    db: Session = Depends(get_db),
):
    """
    **Dry-run: test the NL Intake Layer without generating questions.**

    Pass any natural-language request and see exactly what the AI interpreter
    understood — unit IDs, question counts, marks, difficulty — before running
    the full pipeline.

    **MCQ examples:**
    - `"Create 10 MCQs from Unit 1 and 2, 1 mark each"`
    - `"5 questions from unit 1, 10 from unit 2, 2 marks per question — MCQ"`

    **Subjective examples:**
    - `"Q1 from Unit 1, Q2 from Unit 2, Q3 from Unit 3 — 4 sub-questions each, attempt any 2, 5 marks each"`
    - `"Create a 30-mark paper: 3 long questions from Unit 1 to 3, 10 marks each"`
    """
    subject = db.query(Subject).filter(Subject.id == request.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail=f"Subject {request.subject_id} not found")

    log.info(f"[PARSE] subject={request.subject_id}: '{request.request_text[:100]}'")

    try:
        spec = await interpret_nl_request(
            request_text=request.request_text,
            subject_id=request.subject_id,
            db=db,
            difficulty_override=request.difficulty,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"NL interpretation failed: {e}")
    except Exception as e:
        log.error(f"[PARSE] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Interpretation error: {e}")

    # Build human-readable unit summary using real unit names
    unit_names = {
        u.id: u.name
        for u in db.query(Unit).filter(Unit.subject_id == request.subject_id).all()
    }

    if isinstance(spec, MCQSpec):
        total_marks = spec.total_marks
        total_questions = spec.total_questions
        unit_summary = [
            {
                "unit_id": u.unit_id,
                "unit_name": unit_names.get(u.unit_id, f"Unit {u.unit_id}"),
                "count": u.count,
                "marks": u.count * spec.marks_per_question,
            }
            for u in spec.unit_distribution
        ]
    else:  # SubjectiveSpec
        total_marks = spec.total_marks
        total_questions = sum(s.sub_questions for s in spec.sections)
        unit_summary = [
            {
                "unit_id": s.unit_id,
                "unit_name": unit_names.get(s.unit_id, f"Unit {s.unit_id}"),
                "sub_questions": s.sub_questions,
                "attempt": s.attempt,
                "marks_per_sub": s.marks_per_sub,
                "section_marks": s.section_marks,
                "question_type": s.question_type,
            }
            for s in spec.sections
        ]

    log.info(f"[PARSE] OK — type={spec.type}, marks={total_marks}, questions={total_questions}")

    return ParsedSpecResponse(
        subject_id=request.subject_id,
        request_text=request.request_text,
        parsed_type=spec.type,
        spec=spec.model_dump(),
        total_marks=total_marks,
        total_questions=total_questions,
        unit_summary=unit_summary,
    )


# ─── NL Process Prompt (Preview before generation) ────────────────────────────

@router.post("/process-prompt", response_model=ExamStructurePreview)
async def process_prompt(
    request: NLGenerateRequest,
    db: Session = Depends(get_db),
):
    """
    **Process natural language prompt and show structured preview.**

    Similar to TOC normalization for documents — this endpoint:
    1. Parses teacher's natural language request
    2. Returns a structured, human-readable preview
    3. Shows EXACTLY what will be generated (before actual generation)

    Teacher workflow:
    1. Type NL request (e.g., "create 10 MCQs from unit 1, 2 marks each")
    2. Click "Process Prompt"
    3. Review structured preview (this endpoint)
    4. Approve → call /approve-and-generate

    **MCQ examples:**
    - `"Create 10 MCQs from Unit 1 and 2, 1 mark each"`
    - `"5 questions from unit 1, 10 from unit 2, 2 marks per question — MCQ"`

    **Subjective examples:**
    - `"Q1 from Unit 1, Q2 from Unit 2, Q3 from Unit 3 — 4 sub-questions each, attempt any 2, 5 marks each"`
    - `"Create a 30-mark paper: 3 long questions from Unit 1 to 3, 10 marks each"`

    **Preview Response:**
    - Human-readable structure (NOT raw JSON)
    - Shows: sections, questions, marks breakdown, unit mapping
    - Includes parsed spec for /approve-and-generate
    """
    subject = db.query(Subject).filter(Subject.id == request.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail=f"Subject {request.subject_id} not found")

    log.info(f"[PROCESS PROMPT] subject={request.subject_id}: '{request.request_text[:100]}'")

    # Step 1: Interpret NL request
    try:
        spec = await interpret_nl_request(
            request_text=request.request_text,
            subject_id=request.subject_id,
            db=db,
            difficulty_override=request.difficulty,
            question_type_preference=request.question_type_preference,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"NL interpretation failed: {e}")
    except Exception as e:
        log.error(f"[PROCESS PROMPT] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Interpretation error: {e}")

    # Step 2: Format as structured preview
    try:
        preview = format_exam_preview(
            spec=spec,
            subject_id=request.subject_id,
            request_text=request.request_text,
            db=db,
        )
    except Exception as e:
        log.error(f"[PROCESS PROMPT] Preview formatting error: {e}")
        raise HTTPException(status_code=500, detail=f"Preview formatting error: {e}")

    log.info(f"[PROCESS PROMPT] OK — type={spec.type}, marks={preview.total_marks}, questions={preview.total_questions}")

    return preview


# ─── Approve and Generate ──────────────────────────────────────────────────────

@router.post("/approve-and-generate", response_model=GeneratePaperResponse)
async def approve_and_generate(
    request: ApproveAndGenerateRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    **Generate questions from an approved spec (MCQ or Subjective).**

    This is Step 2 of the NL workflow:
    1. Teacher typed NL request → got TOC preview from /preview
    2. Teacher reviewed/edited the spec → submits here
    3. System generates actual questions and saves as paper

    **Input:**
    - `spec`: The MCQSpec or SubjectiveSpec dict (can be edited by teacher)
    - `spec_type`: "mcq" or "subjective"
    - `subject_id`: Subject ID

    **Output:**
    - Complete generated paper with all questions, answer keys, marking schemes
    - Saved to database with paper_id

    **Process:**
    - Converts spec into QuestionSpecs
    - Retrieves relevant content chunks
    - Generates questions via GPT
    - Assembles and validates paper
    - Saves to PostgreSQL
    """
    subject = db.query(Subject).filter(Subject.id == request.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail=f"Subject {request.subject_id} not found")

    log.info("=" * 60)
    log.info(f"[APPROVE & GENERATE START] subject={request.subject_id}, type={request.spec_type}")
    
    # ── Validate paper_type matches spec_type ──────────────────────────────
    if request.paper_type:
        if request.paper_type == "mcq" and request.spec_type != "mcq":
            raise HTTPException(
                status_code=400, 
                detail="This spec will generate subjective questions. Use Subjective Exam page."
            )
        elif request.paper_type == "subjective" and request.spec_type == "mcq":
            raise HTTPException(
                status_code=400, 
                detail="This spec will generate MCQ questions. Use MCQ Test page."
            )

    # ── Parse spec from dict ────────────────────────────────────────────────
    try:
        if request.spec_type == "mcq":
            spec = MCQSpec(**request.spec)
        elif request.spec_type == "subjective":
            spec = SubjectiveSpec(**request.spec)
        else:
            raise ValueError(f"Invalid spec_type: {request.spec_type}")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid spec: {e}")

    log.info(f"[SPEC] Parsed {request.spec_type} spec: {spec.total_marks}M, {spec.total_questions if hasattr(spec, 'total_questions') else 'N/A'}Q")

    # ── Convert to QuestionSpecs ────────────────────────────────────────────
    question_specs: List[QuestionSpec] = []

    if isinstance(spec, MCQSpec):
        # MCQ: Create one spec per question
        question_no = 1
        for dist in spec.unit_distribution:
            for _ in range(dist.count):
                question_specs.append(
                    QuestionSpec(
                        question_no=question_no,
                        units=[dist.unit_id],
                        marks=spec.marks_per_question,
                        bloom_targets=spec.bloom_levels if spec.bloom_levels else ["understand"],
                        difficulty=spec.difficulty,
                        question_type="mcq",
                        nature=None,
                    )
                )
                question_no += 1
    else:  # SubjectiveSpec
        # Subjective: Create specs for each sub-question in each section
        question_no = 1
        min_diagram = getattr(spec, "min_diagram_questions", 0) or 0
        for section in spec.sections:
            for _ in range(section.sub_questions):
                require_diagram = min_diagram > 0 and question_no <= min_diagram
                question_specs.append(
                    QuestionSpec(
                        question_no=question_no,
                        units=[section.unit_id],
                        marks=section.marks_per_sub,
                        bloom_targets=["understand", "apply"],
                        difficulty=spec.difficulty,
                        question_type="descriptive",
                        nature=section.question_type,
                        require_diagram=require_diagram,
                    )
                )
                question_no += 1

    log.info(f"[SPECS] Created {len(question_specs)} QuestionSpecs")

    # ── Retrieve + Generate + CO Map per question ───────────────────────────
    co_map = get_co_map_for_subject(db, request.subject_id)
    questions_per_spec: dict = {}
    used_chunk_ids_this_run: List[int] = []

    for spec_item in question_specs:
        # CO mapping
        spec_item.co_mapped = map_co(spec_item.units, db, request.subject_id)
        log.info(f"[Q{spec_item.question_no}] CO={spec_item.co_mapped}, units={spec_item.units}")

        # Retrieve chunks
        log.info(f"[Q{spec_item.question_no}] Retrieving chunks (excluding {len(used_chunk_ids_this_run)} used)...")
        chunks = retrieve_chunks_for_spec(
            db, spec_item, request.subject_id, 
            top_k=6, 
            exclude_chunk_ids=used_chunk_ids_this_run
        )
        log.info(f"[Q{spec_item.question_no}] Got {len(chunks)} chunks")

        if not chunks:
            log.warning(f"[Q{spec_item.question_no}] No chunks, trying fallback (any unit)...")
            fallback_spec = QuestionSpec(
                question_no=spec_item.question_no,
                units=[],
                marks=spec_item.marks,
                bloom_targets=spec_item.bloom_targets,
                difficulty=spec_item.difficulty,
                question_type=spec_item.question_type,
            )
            chunks = retrieve_chunks_for_spec(
                db, fallback_spec, request.subject_id,
                top_k=6,
                exclude_chunk_ids=used_chunk_ids_this_run,
            )
            log.info(f"[Q{spec_item.question_no}] Fallback got {len(chunks)} chunks")
        if not chunks and used_chunk_ids_this_run:
            log.warning(f"[Q{spec_item.question_no}] Pool exhausted ({len(used_chunk_ids_this_run)} used), allowing re-use with penalty...")
            reuse_spec = QuestionSpec(
                question_no=spec_item.question_no,
                units=[],
                marks=spec_item.marks,
                bloom_targets=spec_item.bloom_targets,
                difficulty=spec_item.difficulty,
                question_type=spec_item.question_type,
            )
            chunks = retrieve_chunks_for_spec(
                db, reuse_spec, request.subject_id,
                top_k=6,
                exclude_chunk_ids=[],
            )
            log.info(f"[Q{spec_item.question_no}] Re-use got {len(chunks)} chunks")

        used_chunk_ids_this_run.extend(c.id for c in chunks)

        # Retrieve visual chunks: always for require_diagram; optional for other descriptive
        visual_chunks = []
        if spec_item.question_type == "descriptive" and (spec_item.units or getattr(spec_item, "require_diagram", False)):
            top_k_visual = 4 if getattr(spec_item, "require_diagram", False) else (3 if getattr(subject, "math_mode", False) else 2)
            visual_chunks = retrieve_visual_chunks_for_spec(
                db, spec_item, request.subject_id, top_k=top_k_visual
            )
            if getattr(spec_item, "require_diagram", False) and not visual_chunks:
                all_unit_ids = [u.id for u in db.query(Unit).filter(Unit.subject_id == request.subject_id).order_by(Unit.order).all()]
                if all_unit_ids:
                    fallback_spec = QuestionSpec(
                        question_no=spec_item.question_no,
                        units=all_unit_ids,
                        marks=spec_item.marks,
                        bloom_targets=spec_item.bloom_targets,
                        difficulty=spec_item.difficulty,
                        question_type="descriptive",
                    )
                    visual_chunks = retrieve_visual_chunks_for_spec(db, fallback_spec, request.subject_id, top_k=4)
                    if visual_chunks:
                        log.info(f"[Q{spec_item.question_no}] Diagram fallback: got {len(visual_chunks)} visual(s) from any unit")
            if visual_chunks:
                log.info(f"[Q{spec_item.question_no}] Using {len(visual_chunks)} visual chunk(s)")

        # Table MD: chunks store table rows, not full Markdown; fetch from ParsedElement for context
        table_md = get_table_markdown_for_chunks(db, chunks)

        # Extra instruction: diagram-required + math_mode preference
        extra_instruction = request.generation_instruction or ""
        if getattr(spec_item, "require_diagram", False) and visual_chunks:
            extra_instruction = (extra_instruction.strip() + "\n" if extra_instruction.strip() else "") + "This question MUST be based on the provided figure/diagram. The question must explicitly refer to the diagram; the answer key must reference it. Do not ask a generic text-only question."
        if getattr(subject, "math_mode", False) and extra_instruction.strip() and "MUST be based" not in extra_instruction:
            extra_instruction = extra_instruction.strip() + "\nWhen context includes tables or figures, prefer questions that use them (e.g. interpret a table, refer to a diagram)."
        elif getattr(subject, "math_mode", False) and not extra_instruction.strip():
            extra_instruction = "When context includes tables or figures, prefer questions that use them (e.g. interpret a table, refer to a diagram)."

        # Generate question
        log.info(f"[Q{spec_item.question_no}] Generating {spec_item.question_type} ({spec_item.marks}M)...")
        try:
            generated = await generate_question(
                spec_item, chunks, visual_chunks=visual_chunks,
                extra_instruction=extra_instruction.strip() or None,
                table_markdown_context=table_md or None,
            )
            generated.co_mapped = spec_item.co_mapped
            log.info(f"[Q{spec_item.question_no}] OK — bloom={generated.bloom_level}")
        except Exception as e:
            log.error(f"[Q{spec_item.question_no}] ERROR: {e}")
            from generation.schemas import GeneratedQuestion, MarkingPoint
            generated = GeneratedQuestion(
                question_type=spec_item.question_type,
                question_text=f"[Q{spec_item.question_no} generation failed]",
                bloom_level=spec_item.bloom_targets[0] if spec_item.bloom_targets else "understand",
                difficulty=spec_item.difficulty,
                marks=spec_item.marks,
                answer_key="",
                options=[],
                marking_scheme=[MarkingPoint(point="Full answer", marks=spec_item.marks)],
                source_chunk_ids=[c.id for c in chunks],
                source_asset_ids=[],
                co_mapped=spec_item.co_mapped,
                unit_ids=spec_item.units,
            )

        questions_per_spec[spec_item.question_no] = generated

    # ── Assemble paper ──────────────────────────────────────────────────────
    log.info("[ASSEMBLY] Building paper from generated questions...")
    from generation.schemas import BlueprintSpec
    blueprint = BlueprintSpec(
        subject_id=request.subject_id,
        total_marks=spec.total_marks,
        questions=question_specs,
    )
    paper = assemble_paper(blueprint, questions_per_spec, co_map)
    log.info(f"[ASSEMBLY] OK — {len(paper.sections)} sections")

    # ── Validation ──────────────────────────────────────────────────────────
    log.info("[VALIDATION] Running post-processing...")
    paper = await validate_paper(paper)
    log.info("[VALIDATION] OK")

    # ── Save to DB ──────────────────────────────────────────────────────────
    log.info("[DB] Saving paper...")
    paper_dict = paper.model_dump(mode="json")
    
    # Determine paper_type from spec_type
    paper_type_enum = PaperType.MCQ if request.spec_type == "mcq" else PaperType.SUBJECTIVE
    
    db_paper = GeneratedPaper(
        subject_id=request.subject_id,
        paper_type=paper_type_enum,
        pattern_text=f"NL: {request.spec.get('type', 'unknown')} spec",
        total_marks=spec.total_marks,
        paper_json=paper_dict,
        finalised=False,
        teacher_id=current_teacher.id,
    )
    db.add(db_paper)
    db.commit()
    db.refresh(db_paper)
    log.info(f"[DB] Saved as paper_id={db_paper.id} (owner={current_teacher.id})")

    # ── Usage tracking ──────────────────────────────────────────────────────
    paper.paper_id = db_paper.id
    used_chunk_ids = collect_used_chunk_ids(paper)
    increment_usage(db, used_chunk_ids)
    log.info(f"[USAGE] Tracked {len(used_chunk_ids)} chunks")

    log.info("=" * 60)
    log.info(f"[DONE] paper_id={db_paper.id}")
    log.info("=" * 60)

    return GeneratePaperResponse(
        paper_id=db_paper.id,
        subject_id=request.subject_id,
        total_marks=spec.total_marks,
        sections_count=len(paper.sections),
        paper=paper,
    )


# ─── Generate Paper ────────────────────────────────────────────────────────────

@router.post("/generate-paper", response_model=GeneratePaperResponse)
async def generate_paper(
    subject_id: int = Form(..., description="Subject ID"),
    total_marks: int = Form(..., description="Total marks for the paper"),
    pattern_text: Optional[str] = Form(None, description="Pattern as plain text"),
    difficulty_preference: Optional[str] = Form(None, description="easy | medium | hard | auto"),
    pattern_file: Optional[UploadFile] = File(None, description="Pattern as PDF file"),
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    Generate a complete question paper from a pattern.

    Input: subject_id + pattern (text or PDF) + total_marks + optional difficulty
    Output: Full PaperOutput with sections, variants, answer keys, marking schemes
    """
    log.info("=" * 60)
    log.info(f"[PIPELINE START] subject={subject_id}, marks={total_marks}, difficulty={difficulty_preference}")

    # ── Validation ─────────────────────────────────────────────────────────
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail=f"Subject {subject_id} not found")

    if not pattern_text and not pattern_file:
        raise HTTPException(
            status_code=400,
            detail="Provide either pattern_text or pattern_file (PDF)"
        )

    # ── Step 1: Pattern Interpretation ─────────────────────────────────────
    log.info("[STEP 1] Interpreting pattern via GPT...")
    try:
        if pattern_file:
            pdf_bytes = await pattern_file.read()
            parsed_pattern = await interpret_pattern_from_pdf(pdf_bytes, total_marks)
        else:
            parsed_pattern = await interpret_pattern(pattern_text, total_marks)
    except Exception as e:
        log.error(f"[STEP 1] FAILED: {e}")
        raise HTTPException(status_code=422, detail=f"Pattern interpretation failed: {e}")

    if not parsed_pattern.questions:
        raise HTTPException(status_code=422, detail="No questions parsed from pattern")

    log.info(f"[STEP 1] OK — {len(parsed_pattern.questions)} questions parsed:")
    for q in parsed_pattern.questions:
        log.info(f"         Q{q.question_no}: type={q.question_type}, marks={q.marks}, units={q.units}, bloom={q.expected_bloom}")

    # ── Step 2: Blueprint Builder ───────────────────────────────────────────
    log.info("[STEP 2] Building blueprint...")
    blueprint = build_blueprint(parsed_pattern, subject_id, difficulty_preference, db=db)
    log.info(f"[STEP 2] OK — {len(blueprint.questions)} specs built")
    for spec in blueprint.questions:
        log.info(f"         Q{spec.question_no}: type={spec.question_type}, bloom={spec.bloom_targets}, diff={spec.difficulty}")

    # ── Step 3–5: Retrieve + Generate + CO Map per question ────────────────
    co_map = get_co_map_for_subject(db, subject_id)
    questions_per_spec: dict = {}
    used_chunk_ids_this_run: List[int] = []   # Tracks chunks used so far → prevents repetition

    for spec in blueprint.questions:
        log.info(f"[STEP 3] Q{spec.question_no}: CO-mapping units={spec.units}...")
        spec.co_mapped = map_co(spec.units, db, subject_id)
        log.info(f"[STEP 3] Q{spec.question_no}: co_mapped={spec.co_mapped}")

        log.info(f"[STEP 3] Q{spec.question_no}: Retrieving chunks for units={spec.units} (excluding {len(used_chunk_ids_this_run)} already-used)...")
        chunks = retrieve_chunks_for_spec(db, spec, subject_id, top_k=6, exclude_chunk_ids=used_chunk_ids_this_run)
        log.info(f"[STEP 3] Q{spec.question_no}: Got {len(chunks)} chunks")

        if not chunks:
            log.warning(f"[STEP 3] Q{spec.question_no}: No chunks found, trying subject-wide fallback...")
            fallback_spec = QuestionSpec(
                question_no=spec.question_no,
                units=[],
                marks=spec.marks,
                bloom_targets=spec.bloom_targets,
                difficulty=spec.difficulty,
                nature=spec.nature,
                question_type=spec.question_type,
            )
            chunks = retrieve_chunks_for_spec(db, fallback_spec, subject_id, top_k=6, exclude_chunk_ids=used_chunk_ids_this_run)
            log.info(f"[STEP 3] Q{spec.question_no}: Fallback got {len(chunks)} chunks")
        if not chunks and used_chunk_ids_this_run:
            log.warning(f"[STEP 3] Q{spec.question_no}: Pool exhausted ({len(used_chunk_ids_this_run)} used), allowing re-use with penalty...")
            reuse_spec = QuestionSpec(
                question_no=spec.question_no,
                units=[],
                marks=spec.marks,
                bloom_targets=spec.bloom_targets,
                difficulty=spec.difficulty,
                nature=spec.nature,
                question_type=spec.question_type,
            )
            chunks = retrieve_chunks_for_spec(db, reuse_spec, subject_id, top_k=6, exclude_chunk_ids=[])
            log.info(f"[STEP 3] Q{spec.question_no}: Re-use got {len(chunks)} chunks")

        # Mark these chunks as used for subsequent questions
        used_chunk_ids_this_run.extend(c.id for c in chunks)

        # Optional: retrieve visual chunks for subjective/diagram questions
        visual_chunks = []
        if spec.question_type == "descriptive" and spec.units:
            visual_chunks = retrieve_visual_chunks_for_spec(db, spec, subject_id, top_k=2)
            if visual_chunks:
                log.info(f"[STEP 3] Q{spec.question_no}: Using {len(visual_chunks)} visual chunk(s)")

        table_md = get_table_markdown_for_chunks(db, chunks)

        # Step 4: Generate question
        log.info(f"[STEP 4] Q{spec.question_no}: Generating ({spec.question_type}, {spec.marks}M, bloom={spec.bloom_targets})...")
        try:
            generated = await generate_question(
                spec, chunks, visual_chunks=visual_chunks, table_markdown_context=table_md or None
            )
            generated.co_mapped = spec.co_mapped
            log.info(f"[STEP 4] Q{spec.question_no}: OK — question_type={generated.question_type}, options={len(generated.options)}, bloom={generated.bloom_level}")
            if generated.question_type == "mcq":
                for opt in generated.options:
                    log.info(f"         {opt.label}: {opt.text[:60]}")
                log.info(f"         Answer: {generated.answer_key}")
        except Exception as e:
            log.error(f"[STEP 4] Q{spec.question_no}: ERROR — {e}")
            from generation.schemas import GeneratedQuestion, MarkingPoint
            generated = GeneratedQuestion(
                question_type=spec.question_type,
                question_text=f"[Q{spec.question_no} generation failed — please retry]",
                bloom_level=spec.bloom_targets[0] if spec.bloom_targets else "understand",
                difficulty=spec.difficulty,
                marks=spec.marks,
                answer_key="",
                options=[],
                marking_scheme=[MarkingPoint(point="Full answer", marks=spec.marks)],
                source_chunk_ids=[c.id for c in chunks],
                source_asset_ids=[],
                co_mapped=spec.co_mapped,
                unit_ids=spec.units,
            )

        questions_per_spec[spec.question_no] = generated

    # ── Step 6: Paper Assembly ─────────────────────────────────────────────
    log.info("[STEP 6] Assembling paper...")
    paper = assemble_paper(blueprint, questions_per_spec, co_map)
    log.info(f"[STEP 6] OK — {len(paper.sections)} sections assembled")

    # ── Step 7: Validation ─────────────────────────────────────────────────
    log.info("[STEP 7] Running post-processing validation...")
    paper = await validate_paper(paper)
    log.info("[STEP 7] OK — validation complete")

    # ── Step 9: Store in DB ─────────────────────────────────────────────────
    log.info("[STEP 9] Saving paper to PostgreSQL...")
    paper_dict = paper.model_dump(mode="json")
    
    # Infer paper_type from questions
    all_mcq = all(
        q.question.question_type == "mcq"
        for section in paper.sections
        for variant in section.variants
        for q in [variant]
        if hasattr(q, 'question')
    )
    paper_type_enum = PaperType.MCQ if all_mcq else PaperType.SUBJECTIVE
    
    db_paper = GeneratedPaper(
        subject_id=subject_id,
        paper_type=paper_type_enum,
        pattern_text=pattern_text or (
            f"PDF: {pattern_file.filename}" if pattern_file else "unknown"
        ),
        total_marks=total_marks,
        paper_json=paper_dict,
        finalised=False,
        teacher_id=current_teacher.id,
    )
    db.add(db_paper)
    db.commit()
    db.refresh(db_paper)
    log.info(f"[STEP 9] OK — saved as paper_id={db_paper.id} (owner={current_teacher.id})")

    # ── Step 8: Usage Tracking ──────────────────────────────────────────────
    paper.paper_id = db_paper.id
    used_chunk_ids = collect_used_chunk_ids(paper)
    increment_usage(db, used_chunk_ids)
    log.info(f"[STEP 8] Usage tracked — {len(used_chunk_ids)} chunk IDs")
    log.info("=" * 60)
    log.info(f"[PIPELINE DONE] paper_id={db_paper.id}")
    log.info("=" * 60)

    return GeneratePaperResponse(
        paper_id=db_paper.id,
        subject_id=subject_id,
        total_marks=total_marks,
        sections_count=len(paper.sections),
        paper=paper,
    )


# ─── Paper access: owner or shared with current teacher ───────────────────────

def _paper_owned_by(paper: GeneratedPaper, teacher_id: int) -> bool:
    return paper.teacher_id == teacher_id


def _paper_shared_with(db: Session, paper_id: int, teacher_id: int) -> bool:
    return db.query(PaperShare).filter(
        PaperShare.paper_id == paper_id,
        PaperShare.shared_with_id == teacher_id,
    ).first() is not None


def _can_view_paper(db: Session, paper: GeneratedPaper, teacher_id: int) -> bool:
    return _paper_owned_by(paper, teacher_id) or _paper_shared_with(db, paper.id, teacher_id)


# ─── List Papers ───────────────────────────────────────────────────────────────

@router.get("/papers", response_model=List[PaperSummary])
def list_papers(
    subject_id: Optional[int] = None,
    limit: int = 20,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """List papers the current teacher owns or that were shared with them."""
    shared_paper_ids = db.query(PaperShare.paper_id).filter(
        PaperShare.shared_with_id == current_teacher.id,
    ).distinct()
    q = db.query(GeneratedPaper).filter(
        or_(
            GeneratedPaper.teacher_id == current_teacher.id,
            GeneratedPaper.id.in_(shared_paper_ids),
        )
    )
    if subject_id is not None:
        q = q.filter(GeneratedPaper.subject_id == subject_id)
    papers = q.order_by(GeneratedPaper.id.desc()).limit(limit).all()
    return [
        PaperSummary(
            paper_id=p.id,
            subject_id=p.subject_id,
            paper_type=p.paper_type.value if p.paper_type else None,
            total_marks=p.total_marks,
            sections_count=len((p.paper_json or {}).get("sections", [])),
            created_at=p.created_at,
            finalised=p.finalised or False,
        )
        for p in papers
    ]


# ─── Delete Paper ──────────────────────────────────────────────────────────────

@router.delete("/papers/{paper_id}")
def delete_paper(
    paper_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Permanently delete a generated paper. Only the owner can delete."""
    p = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not _paper_owned_by(p, current_teacher.id):
        raise HTTPException(status_code=403, detail="Only the paper owner can delete it")
    db.delete(p)
    db.commit()
    return {"ok": True, "deleted_paper_id": paper_id}


# ─── Get Paper ─────────────────────────────────────────────────────────────────

@router.get("/papers/{paper_id}", response_model=PaperOutput)
def get_paper(
    paper_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Get full paper JSON. Allowed if you own the paper or it was shared with you."""
    p = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not _can_view_paper(db, p, current_teacher.id):
        raise HTTPException(status_code=404, detail="Paper not found")
    data = dict(p.paper_json or {})
    data["paper_id"] = p.id
    return PaperOutput(**data)


# ─── CO Map ────────────────────────────────────────────────────────────────────

@router.get("/co-map/{subject_id}")
def co_map_for_subject(subject_id: int, db: Session = Depends(get_db)):
    """Return unit_id → CO label mapping for a subject (for frontend display)."""
    co_map = get_co_map_for_subject(db, subject_id)
    units = db.query(Unit).filter(Unit.subject_id == subject_id).order_by(Unit.order).all()
    return {
        "subject_id": subject_id,
        "co_map": {
            str(uid): {"co": co, "unit_id": uid}
            for uid, co in co_map.items()
        },
        "units": [
            {"id": u.id, "name": u.name, "order": u.order, "co": co_map.get(u.id, "CO?")}
            for u in units
        ],
    }


# ─── Human-in-the-loop: Edit Question ─────────────────────────────────────────

class EditQuestionRequest(BaseModel):
    section_index: int          # 0-based index in paper.sections
    variant_index: int          # 0-based index in section.variants (0 or 1 for OR pair)
    question_text: str
    answer_key: Optional[str] = None
    marking_scheme: Optional[list] = None   # [{"point": str, "marks": int}]


@router.patch("/papers/{paper_id}/question")
def edit_question(
    paper_id: int,
    req: EditQuestionRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    Human-in-the-loop: Update a specific question's text, answer key, or marking scheme.
    Only the paper owner can edit.
    """
    p = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not _paper_owned_by(p, current_teacher.id):
        raise HTTPException(status_code=403, detail="Only the paper owner can edit it")

    data = dict(p.paper_json or {})
    sections = data.get("sections", [])

    if req.section_index >= len(sections):
        raise HTTPException(status_code=400, detail="Invalid section_index")

    section = sections[req.section_index]
    variants = section.get("variants", [])

    if req.variant_index >= len(variants):
        raise HTTPException(status_code=400, detail="Invalid variant_index")

    q = variants[req.variant_index]["question"]
    q["question_text"] = req.question_text
    if req.answer_key is not None:
        q["answer_key"] = req.answer_key
    if req.marking_scheme is not None:
        q["marking_scheme"] = req.marking_scheme

    # Mark as human-edited
    q["human_edited"] = True

    # Persist
    from sqlalchemy import update
    db.execute(
        update(GeneratedPaper)
        .where(GeneratedPaper.id == paper_id)
        .values(paper_json=data)
    )
    db.commit()

    return {"ok": True, "paper_id": paper_id}


# ─── Human-in-the-loop: Regenerate Single Question ────────────────────────────

class RegenerateQuestionRequest(BaseModel):
    section_index: int
    variant_index: int
    subject_id: int
    unit_ids: List[int] = []
    marks: int
    bloom_targets: List[str] = ["understand"]
    difficulty: str = "medium"
    nature: Optional[str] = None
    question_type: str = "descriptive"   # ← Added: pass MCQ type through


@router.post("/papers/{paper_id}/regenerate-question")
async def regenerate_question(
    paper_id: int,
    req: RegenerateQuestionRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    Human-in-the-loop: Regenerate a single question using the same spec.
    Only the paper owner can regenerate.
    """
    from generation.retrieval_engine import retrieve_chunks_for_spec
    from generation.question_generator import generate_question

    p = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not _paper_owned_by(p, current_teacher.id):
        raise HTTPException(status_code=403, detail="Only the paper owner can regenerate questions")

    spec = QuestionSpec(
        question_no=req.section_index + 1,
        units=req.unit_ids,
        marks=req.marks,
        bloom_targets=req.bloom_targets,
        difficulty=req.difficulty,
        nature=req.nature,
        question_type=req.question_type,   # ← CRITICAL: preserve MCQ type
    )

    log.info(f"[REGEN] section={req.section_index}, type={req.question_type}, marks={req.marks}")

    # Retrieve fresh chunks
    chunks = retrieve_chunks_for_spec(db, spec, req.subject_id, top_k=5)
    if not chunks:
        spec.units = []
        chunks = retrieve_chunks_for_spec(db, spec, req.subject_id, top_k=5)

    # Optional: visual chunks for descriptive questions
    visual_chunks = []
    if spec.question_type == "descriptive" and spec.units:
        visual_chunks = retrieve_visual_chunks_for_spec(db, spec, req.subject_id, top_k=2)

    table_md = get_table_markdown_for_chunks(db, chunks)

    log.info(f"[REGEN] Got {len(chunks)} chunks, generating...")

    # Generate
    try:
        generated = await generate_question(
            spec, chunks, visual_chunks=visual_chunks, table_markdown_context=table_md or None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {e}")

    log.info(f"[REGEN] OK — type={generated.question_type}, options={len(generated.options)}")

    # Patch into paper_json
    data = dict(p.paper_json or {})
    sections = data.get("sections", [])

    if req.section_index >= len(sections):
        raise HTTPException(status_code=400, detail="Invalid section_index")

    variants = sections[req.section_index].get("variants", [])
    if req.variant_index >= len(variants):
        raise HTTPException(status_code=400, detail="Invalid variant_index")

    new_q = generated.model_dump(mode="json")
    new_q["human_edited"] = False
    variants[req.variant_index]["question"] = new_q

    from sqlalchemy import update
    db.execute(
        update(GeneratedPaper)
        .where(GeneratedPaper.id == paper_id)
        .values(paper_json=data)
    )
    db.commit()

    return {"ok": True, "question": new_q}


# ─── Human-in-the-loop: Finalise Paper ────────────────────────────────────────

@router.patch("/papers/{paper_id}/finalise")
def finalise_paper(
    paper_id: int,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Mark a paper as finalised. Only the paper owner can finalise."""
    p = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not _paper_owned_by(p, current_teacher.id):
        raise HTTPException(status_code=403, detail="Only the paper owner can finalise it")

    # Write to the DB column (not the JSON blob) so list_papers can read it
    from sqlalchemy import update
    db.execute(
        update(GeneratedPaper)
        .where(GeneratedPaper.id == paper_id)
        .values(finalised=True)
    )
    db.commit()
    log.info(f"[FINALISE] paper_id={paper_id} marked as finalised")
    return {"ok": True, "paper_id": paper_id, "finalised": True}


# ─── Export: Question Paper PDF ────────────────────────────────────────────────

from fastapi.responses import StreamingResponse

@router.get("/papers/{paper_id}/export/question-paper")
def export_question_paper(
    paper_id: int,
    college_name: Optional[str] = None,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    Export question paper as PDF. Allowed if you own the paper or it was shared with you.
    """
    from generation.paper_exporter import generate_question_paper

    db_paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id).first()
    if not db_paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not _can_view_paper(db, db_paper, current_teacher.id):
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Get subject name
    subject = db.query(Subject).filter(Subject.id == db_paper.subject_id).first()
    subject_name = subject.name if subject else "Unknown Subject"
    
    # Parse paper JSON
    paper = PaperOutput(**db_paper.paper_json)
    
    # Resolve source_asset_ids → image paths (same order as sections/variants)
    question_image_paths = []
    for section in paper.sections:
        for variant in section.variants:
            asset_ids = getattr(variant.question, "source_asset_ids", None) or []
            if not asset_ids:
                question_image_paths.append([])
                continue
            rows = db.query(VisualChunk).filter(VisualChunk.id.in_(asset_ids)).all()
            id_to_path = {r.id: r.image_path for r in rows if r.image_path}
            paths = [id_to_path[aid] for aid in asset_ids if aid in id_to_path]
            question_image_paths.append(paths)
    
    # Generate PDF
    pdf_buffer = generate_question_paper(
        paper=paper,
        subject_name=subject_name,
        college_name=college_name,
        question_image_paths=question_image_paths if any(p for p in question_image_paths) else None,
    )
    
    # Return as streaming response
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=question_paper_{paper_id}.pdf"
        }
    )


@router.get("/papers/{paper_id}/export/answer-key")
def export_answer_key(
    paper_id: int,
    college_name: Optional[str] = None,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    Export answer key PDF. Allowed if you own the paper or it was shared with you.
    """
    from generation.paper_exporter import generate_answer_key

    db_paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id).first()
    if not db_paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not _can_view_paper(db, db_paper, current_teacher.id):
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Get subject name
    subject = db.query(Subject).filter(Subject.id == db_paper.subject_id).first()
    subject_name = subject.name if subject else "Unknown Subject"
    
    # Parse paper JSON
    paper = PaperOutput(**db_paper.paper_json)
    
    # Generate PDF
    pdf_buffer = generate_answer_key(
        paper=paper,
        subject_name=subject_name,
        college_name=college_name,
    )
    
    # Return as streaming response
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=answer_key_{paper_id}.pdf"
        }
    )


@router.get("/papers/{paper_id}/export/marking-scheme")
def export_marking_scheme(
    paper_id: int,
    college_name: Optional[str] = None,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    Export marking scheme PDF. Allowed if you own the paper or it was shared with you.
    """
    from generation.paper_exporter import generate_marking_scheme

    db_paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id).first()
    if not db_paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not _can_view_paper(db, db_paper, current_teacher.id):
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Get subject name
    subject = db.query(Subject).filter(Subject.id == db_paper.subject_id).first()
    subject_name = subject.name if subject else "Unknown Subject"
    
    # Parse paper JSON
    paper = PaperOutput(**db_paper.paper_json)
    
    # Generate PDF
    pdf_buffer = generate_marking_scheme(
        paper=paper,
        subject_name=subject_name,
        college_name=college_name,
    )
    
    # Return as streaming response
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=marking_scheme_{paper_id}.pdf"
        }
    )


# ─── Paper Sharing ─────────────────────────────────────────────────────────────

class SharePaperRequest(BaseModel):
    shared_with_email: EmailStr


class SharePaperResponse(BaseModel):
    message: str
    shared_with: str


@router.post("/papers/{paper_id}/share", response_model=SharePaperResponse)
def share_paper(
    paper_id: int,
    payload: SharePaperRequest,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    Share a generated paper with another teacher by email.
    Only the paper owner can share. Can share with multiple teachers (one call per teacher).
    """
    paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not _paper_owned_by(paper, current_teacher.id):
        raise HTTPException(status_code=403, detail="Only the paper owner can share it")

    recipient = db.query(Teacher).filter(
        Teacher.email == payload.shared_with_email,
        Teacher.is_active == True,
    ).first()
    if not recipient:
        raise HTTPException(status_code=404, detail=f"No active teacher found with email {payload.shared_with_email}")

    if recipient.id == current_teacher.id:
        raise HTTPException(status_code=400, detail="Cannot share a paper with yourself")

    existing = db.query(PaperShare).filter(
        PaperShare.paper_id == paper_id,
        PaperShare.shared_with_id == recipient.id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Paper already shared with this teacher")

    share = PaperShare(
        paper_id=paper_id,
        shared_by_id=current_teacher.id,
        shared_with_id=recipient.id,
    )
    db.add(share)
    db.commit()

    return SharePaperResponse(
        message="Paper shared successfully",
        shared_with=recipient.full_name,
    )
