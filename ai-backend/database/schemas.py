"""
Pydantic schemas for request/response validation
Separate from SQLAlchemy models for clean API contracts
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime


# ==========================================
# CONCEPT SCHEMAS
# ==========================================

class ConceptBase(BaseModel):
    """Base schema for Concept - shared fields"""
    name: str = Field(..., min_length=1, max_length=255, description="Concept name")
    description: Optional[str] = Field(None, description="Detailed concept description")
    diagram_critical: bool = Field(default=False, description="Whether concept requires diagram understanding")
    order: int = Field(default=0, ge=0, description="Display order within unit")


class ConceptCreate(ConceptBase):
    """Schema for creating a new Concept"""
    unit_id: int = Field(..., gt=0, description="Parent unit ID")


class ConceptUpdate(BaseModel):
    """Schema for updating a Concept - all fields optional"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    diagram_critical: Optional[bool] = None
    order: Optional[int] = Field(None, ge=0)


class ConceptResponse(ConceptBase):
    """Schema for Concept response"""
    id: int
    unit_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# UNIT SCHEMAS
# ==========================================

class UnitBase(BaseModel):
    """Base schema for Unit - shared fields"""
    name: str = Field(..., min_length=1, max_length=255, description="Unit name")
    description: Optional[str] = Field(None, description="Unit description")
    order: int = Field(default=0, ge=0, description="Display order within subject")


class UnitCreate(UnitBase):
    """Schema for creating a new Unit"""
    subject_id: int = Field(..., gt=0, description="Parent subject ID")


class UnitUpdate(BaseModel):
    """Schema for updating a Unit - all fields optional"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    order: Optional[int] = Field(None, ge=0)


class UnitResponse(UnitBase):
    """Schema for Unit response without concepts"""
    id: int
    subject_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UnitWithConcepts(UnitResponse):
    """Schema for Unit response with nested concepts"""
    concepts: List[ConceptResponse] = []

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# SUBJECT SCHEMAS
# ==========================================

class SubjectBase(BaseModel):
    """Base schema for Subject - shared fields"""
    name: str = Field(..., min_length=1, max_length=255, description="Subject name")
    description: Optional[str] = Field(None, description="Subject description")


class SubjectCreate(SubjectBase):
    """Schema for creating a new Subject"""
    math_mode: bool = False  # When True, backend sets formula_mode=True, vision_budget=10


class SubjectUpdate(BaseModel):
    """Schema for updating a Subject - all fields optional"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    math_mode: Optional[bool] = None
    formula_mode: Optional[bool] = None
    vision_budget: Optional[int] = None


class SubjectResponse(SubjectBase):
    """Schema for Subject response without units"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    math_mode: bool = False
    formula_mode: bool = False
    vision_budget: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class SubjectWithUnits(SubjectResponse):
    """Schema for Subject response with nested units (no concepts)"""
    units: List[UnitResponse] = []

    model_config = ConfigDict(from_attributes=True)


class SubjectComplete(SubjectResponse):
    """Schema for complete Subject hierarchy with all units and concepts"""
    units: List[UnitWithConcepts] = []

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# BULK CREATION SCHEMAS
# ==========================================

class BulkUnitCreate(BaseModel):
    """Schema for creating multiple units at once"""
    units: List[UnitCreate]


class BulkConceptCreate(BaseModel):
    """Schema for creating multiple concepts at once"""
    concepts: List[ConceptCreate]


# ==========================================
# DOCUMENT SCHEMAS
# ==========================================

class DocumentCreate(BaseModel):
    """Schema for creating a new Document"""
    filename: str = Field(..., min_length=1, max_length=255)
    file_type: str = Field(..., pattern="^(pdf|pptx|docx)$")
    file_size_bytes: int = Field(..., gt=0)
    subject_id: int = Field(..., gt=0)


class DocumentResponse(BaseModel):
    """Schema for Document response"""
    id: int
    filename: str
    file_type: str
    file_size_bytes: int
    subject_id: int
    status: str
    upload_timestamp: datetime
    indexed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# PARSED ELEMENT SCHEMAS
# ==========================================

class ParsedElementCreate(BaseModel):
    """Schema for creating a new ParsedElement"""
    document_id: int = Field(..., gt=0)
    order_index: int = Field(..., ge=0)
    element_type: str = Field(..., min_length=1, max_length=50)
    category: str = Field(..., pattern="^(TEXT|DIAGRAM|TABLE|CODE|FORMULA|OTHER)$")
    text: Optional[str] = None
    page_number: Optional[int] = Field(None, ge=1)
    element_metadata: dict = Field(default_factory=dict)
    is_diagram_critical: bool = False
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)


class ParsedElementResponse(BaseModel):
    """Schema for ParsedElement response"""
    id: int
    document_id: int
    order_index: int
    element_type: str
    category: str
    text: Optional[str] = None
    page_number: Optional[int] = None
    element_metadata: dict
    is_diagram_critical: bool
    confidence_score: Optional[float] = None
    concept_id: Optional[int] = None
    alignment_confidence: Optional[float] = None
    vector_id: Optional[str] = None
    indexed_at: Optional[datetime] = None
    embedding_vector: Optional[list] = None  # 384-dimensional embedding
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# QUESTION BANK (Layer 3) – Contract schema
# ==========================================

QUESTION_TYPES = ("MCQ", "SHORT", "LONG", "NUMERICAL", "DIAGRAM")
BLOOM_LEVELS = ("BT1", "BT2", "BT3", "BT4", "BT5", "BT6")
DIFFICULTY_LEVELS = ("E", "M", "H")


class GeneratorQuestionOutput(BaseModel):
    """Strict schema every generator must output. Contract for validators + storage."""
    question_text: str = Field(..., min_length=1, description="Question stem")
    question_type: str = Field(..., description="MCQ | SHORT | LONG | NUMERICAL | DIAGRAM")
    marks: int = Field(1, ge=1, le=20)
    options: Optional[List[str]] = Field(None, description="For MCQ: 4 options")
    correct_answer: Optional[str] = Field(None, description="For MCQ: letter A/B/C/D or option text")
    answer_key: Optional[dict] = Field(None, description="Rubric, key points, steps for non-MCQ")
    explanation: Optional[str] = Field(None, description="Short reasoning")
    bloom_level: str = Field(..., description="BT1–BT6")
    difficulty: str = Field(..., description="E | M | H")
    concept_id: int = Field(..., gt=0)
    unit_id: int = Field(..., gt=0)
    subject_id: int = Field(..., gt=0)
    co_ids: List[int] = Field(default_factory=list, description="Course outcomes (empty until CO manager)")
    source_chunk_ids: List[int] = Field(default_factory=list, description="Anti-hallucination anchor")
    quality_flags: Optional[dict] = Field(None, description="ambiguity, missing_context, etc.")
    generator_metadata: Optional[dict] = Field(None, description="model, temperature, prompt_version, run_id")


class QuestionBankBase(BaseModel):
    """Fields shared for create/update/response"""
    question_text: str
    question_type: str
    marks: int = 1
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    answer_key: Optional[dict] = None
    explanation: Optional[str] = None
    bloom_level: Optional[str] = None
    difficulty: Optional[str] = None
    concept_id: Optional[int] = None
    unit_id: Optional[int] = None
    subject_id: int = Field(..., gt=0)
    co_ids: List[int] = Field(default_factory=list)
    source_chunk_ids: List[int] = Field(default_factory=list)
    quality_flags: Optional[dict] = None
    generator_metadata: Optional[dict] = None
    status: str = Field(default="pending", description="pending | approved | rejected")


class QuestionBankCreate(QuestionBankBase):
    pass


class QuestionBankUpdate(BaseModel):
    """Teacher edit: only these fields are patchable."""
    question_text: Optional[str] = None
    question_type: Optional[str] = None
    marks: Optional[int] = None
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    answer_key: Optional[dict] = None
    explanation: Optional[str] = None
    bloom_level: Optional[str] = None
    difficulty: Optional[str] = None
    quality_flags: Optional[dict] = None


class QuestionBankResponse(QuestionBankBase):
    id: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class GenerateQuestionsRequest(BaseModel):
    """Request for concept-centric question generation."""
    subject_id: int = Field(..., gt=0)
    unit_id: Optional[int] = Field(None, gt=0)
    concept_id: Optional[int] = Field(None, gt=0)
    target: dict = Field(
        default_factory=lambda: {"mcq": 2, "short": 1, "long": 1},
        description="e.g. {mcq: 20, short: 10, long: 10}",
    )
    constraints: Optional[dict] = Field(None, description="bloom_distribution, difficulty_distribution")
    dry_run: bool = Field(False, description="If true, generate but do not store")

