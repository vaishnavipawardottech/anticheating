"""
Pydantic schemas for the paper generation pipeline.
Supports: descriptive (short/long answer) AND MCQ question types.

Layer 1 (legacy):   PatternInput → pattern text parsing pipeline
Layer 2 (new):      NLGenerateRequest → NL intake layer → MCQSpec | SubjectiveSpec
"""

from typing import List, Optional, Dict, Any, Union, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# ─── Layer 1: Input (legacy pattern-text pipeline) ────────────────────────────

class PatternInput(BaseModel):
    """User-facing request to generate a paper."""
    subject_id: int = Field(..., description="Subject ID")
    pattern_text: Optional[str] = Field(None, description="Pattern in free text (Option B)")
    total_marks: int = Field(..., description="Total marks for the paper", ge=1)
    difficulty_preference: Optional[str] = Field(
        None, description="Global difficulty: easy | medium | hard | auto"
    )


# ─── Internal pipeline types ───────────────────────────────────────────────────

class ParsedQuestion(BaseModel):
    """Raw parsed question spec from Step 1 (LLM output)."""
    question_no: int
    units: List[int] = Field(default_factory=list)
    marks: int
    nature: Optional[str] = None
    question_type: str = "descriptive"   # "mcq" | "descriptive"
    expected_bloom: List[str] = Field(default_factory=list)
    is_or_pair: bool = False
    or_pair_with: Optional[int] = None


class ParsedPattern(BaseModel):
    """Output of Step 1: full parsed pattern."""
    total_marks: int
    questions: List[ParsedQuestion]


class QuestionSpec(BaseModel):
    """Spec for one question block, after blueprint building (Step 2)."""
    question_no: int
    units: List[int]
    marks: int
    bloom_targets: List[str]
    difficulty: str = "medium"
    nature: Optional[str] = None
    question_type: str = "descriptive"   # "mcq" | "descriptive"
    co_mapped: Optional[str] = None
    is_or_pair: bool = False
    or_pair_with: Optional[int] = None


class BlueprintSpec(BaseModel):
    """Full generation blueprint for a paper (Step 2 output)."""
    subject_id: int
    total_marks: int
    questions: List[QuestionSpec]


# ─── Generation output types ───────────────────────────────────────────────────

class MarkingPoint(BaseModel):
    point: str
    marks: int


class MCQOption(BaseModel):
    """One MCQ option."""
    label: str   # "A", "B", "C", "D"
    text: str


class GeneratedQuestion(BaseModel):
    """Single generated question (Step 4 output)."""
    question_type: str = "descriptive"        # "mcq" | "descriptive"
    question_text: str
    bloom_level: str
    difficulty: str
    marks: int
    answer_key: str                           # For MCQ: "A" / "B" / "C" / "D"
    # MCQ-only fields
    options: List[MCQOption] = Field(default_factory=list)
    # Descriptive-only fields
    marking_scheme: List[MarkingPoint] = Field(default_factory=list)
    # Common
    source_chunk_ids: List[int] = Field(default_factory=list)
    co_mapped: Optional[str] = None
    unit_ids: List[int] = Field(default_factory=list)
    human_edited: bool = False


class GeneratedVariant(BaseModel):
    """One variant (Q1 or Q2) in an OR pair."""
    variant_label: str   # e.g. "Q1", "Q2", or "" if not an OR pair
    question: GeneratedQuestion


class PaperSection(BaseModel):
    """One section of the paper (may have 1 or 2 variants for OR questions)."""
    question_no: int
    marks: int
    co_mapped: Optional[str]
    bloom_level: str
    variants: List[GeneratedVariant]  # len == 1 for normal; len == 2 for OR pair


class PaperOutput(BaseModel):
    """Complete generated paper."""
    paper_id: Optional[int] = None
    subject_id: int
    paper_type: str = "subjective"  # "mcq" or "subjective"
    total_marks: int
    sections: List[PaperSection]
    created_at: Optional[datetime] = None
    generation_metadata: Dict[str, Any] = Field(default_factory=dict)


# ─── Layer 1: API request/response ────────────────────────────────────────────

class GeneratePaperResponse(BaseModel):
    paper_id: int
    subject_id: int
    total_marks: int
    sections_count: int
    paper: PaperOutput


class PaperSummary(BaseModel):
    paper_id: int
    subject_id: int
    paper_type: Optional[str] = None  # "mcq" | "subjective"
    total_marks: int
    sections_count: int
    created_at: Optional[datetime]
    finalised: bool = False


# ─── Layer 2: NL Intake Schemas ────────────────────────────────────────────────
# Used by nl_interpreter.py and the new generation endpoints.

class UnitCountSpec(BaseModel):
    """One entry in an MCQ unit distribution: how many questions from each unit."""
    unit_id: int
    count: int = Field(..., ge=1)


class MCQSpec(BaseModel):
    """Fully-typed spec for an MCQ generation run (output of NL interpreter)."""
    type: Literal["mcq"] = "mcq"
    marks_per_question: int = Field(1, ge=1, le=10)
    difficulty: str = "auto"           # easy | medium | hard | auto
    bloom_levels: List[str] = Field(default_factory=list)
    unit_distribution: List[UnitCountSpec]

    @property
    def total_questions(self) -> int:
        return sum(u.count for u in self.unit_distribution)

    @property
    def total_marks(self) -> int:
        return self.total_questions * self.marks_per_question

    @property
    def all_unit_ids(self) -> List[int]:
        return [u.unit_id for u in self.unit_distribution]


class SubjectiveSection(BaseModel):
    """One section of a subjective paper — one unit, multiple sub-questions."""
    unit_id: int
    question_type: str = "short"       # "short" (≤7 marks) | "long" (≥8 marks)
    sub_questions: int = Field(..., ge=1, description="Total questions to generate")
    attempt: int = Field(..., ge=1, description="How many student must answer")
    marks_per_sub: int = Field(..., ge=1, description="Marks per sub-question")

    @property
    def section_marks(self) -> int:
        """Marks contributed by this section = attempt × marks_per_sub."""
        return self.attempt * self.marks_per_sub


class SubjectiveSpec(BaseModel):
    """Fully-typed spec for a subjective generation run (output of NL interpreter)."""
    type: Literal["subjective"] = "subjective"
    total_marks: int
    difficulty: str = "auto"
    sections: List[SubjectiveSection]

    @property
    def all_unit_ids(self) -> List[int]:
        return [s.unit_id for s in self.sections]


# ─── Layer 2: API Request / Response ──────────────────────────────────────────

class NLGenerateRequest(BaseModel):
    """
    Unified natural-language generation request.
    The teacher types anything — the NL interpreter parses it into a typed spec.
    """
    subject_id: int = Field(..., description="Subject ID")
    request_text: str = Field(
        ...,
        description=(
            "Free-text description of what to generate.\n"
            "Examples:\n"
            "  'Create 10 MCQs from Unit 1 and 2, 1 mark each'\n"
            "  '5 MCQs from Unit 1, 10 from Unit 2, 2 marks each'\n"
            "  'Q1 from Unit 1, Q2 from Unit 2, 4 sub-parts each, attempt any 2, 5 marks each'"
        ),
    )
    difficulty: Optional[str] = Field(
        None,
        description="Override difficulty: easy | medium | hard (leave blank for auto)"
    )


class FeedbackRegenRequest(BaseModel):
    """
    HIL: regenerate one question incorporating teacher feedback.
    The feedback string is injected directly into the generation prompt.
    """
    paper_id: int
    section_index: int      # 0-based index in paper.sections
    variant_index: int      # 0-based index in section.variants
    subject_id: int
    unit_ids: List[int] = Field(default_factory=list)
    marks: int = 5
    bloom_targets: List[str] = Field(default_factory=lambda: ["understand"])
    difficulty: str = "medium"
    question_type: str = "descriptive"    # "mcq" | "descriptive"
    feedback: str = Field(
        ...,
        description=(
            "Teacher's feedback on the previous question, e.g. "
            "'Too easy, needs application-level thinking'"
        )
    )


class ParsedSpecResponse(BaseModel):
    """
    Response from POST /generation/parse — shows what the NL interpreter
    understood from a request_text, BEFORE actually generating anything.
    Use this to verify the interpreter's output is correct.
    """
    subject_id: int
    request_text: str
    parsed_type: str              # "mcq" | "subjective"
    spec: Dict[str, Any]          # The full MCQSpec or SubjectiveSpec as a dict
    total_marks: int
    total_questions: int
    unit_summary: List[Dict[str, Any]]   # [{unit_id, unit_name, count}]


# ─── NL Exam Preview Responses ─────────────────────────────────────────────────

class ExamQuestionPreview(BaseModel):
    """Single question preview for NL-generated exams."""
    question_no: int
    unit_id: int
    unit_name: str
    question_type: str           # "mcq" | "short" | "long"
    marks: int
    description: str              # Human-readable description


class ExamSectionPreview(BaseModel):
    """Section preview for subjective papers."""
    section_no: int
    title: str                    # e.g., "Section A - Unit 1: Operating Systems"
    unit_id: int
    unit_name: str
    total_questions: int          # sub_questions
    attempt_required: int         # attempt
    marks_per_question: int       # marks_per_sub
    section_marks: int            # attempt × marks_per_sub
    question_type: str            # "short" | "long"
    note: Optional[str] = None    # e.g., "Attempt any 2 out of 4"


class ExamStructurePreview(BaseModel):
    """
    Exam Structure Preview — shows EXACTLY what will be generated
    in a structured, teacher-friendly format (similar to TOC for documents).
    
    This is shown BEFORE generation. Teacher can:
    1. Approve → proceed to generation
    2. Edit → modify the spec and re-process
    3. Cancel → discard
    """
    subject_id: int
    subject_name: str
    request_text: str
    exam_type: str                 # "MCQ Examination" | "Subjective Examination"
    total_marks: int
    total_questions: int
    difficulty: str
    
    # For MCQ papers
    mcq_preview: Optional[List[ExamQuestionPreview]] = None
    marks_per_question: Optional[int] = None
    
    # For Subjective papers
    sections: Optional[List[ExamSectionPreview]] = None
    
    # Metadata
    parsed_spec: Dict[str, Any]    # The actual MCQSpec or SubjectiveSpec
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ApproveAndGenerateRequest(BaseModel):
    """
    Request to generate a paper from a previously-parsed (and approved) spec.
    The spec can be edited by the teacher before submission.
    """
    subject_id: int
    spec: Dict[str, Any]           # MCQSpec or SubjectiveSpec as dict
    spec_type: str                 # "mcq" | "subjective"
    paper_type: Optional[str] = None  # "mcq" | "subjective" - for validation
