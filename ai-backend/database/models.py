"""
SQLAlchemy models for structure truth layer
Subject → Unit → Concept hierarchy

These models are the SOURCE OF TRUTH for academic structure.
NO document references, NO embeddings, NO vectors here.
"""

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Float, JSON
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from database.database import Base


class Subject(Base):
    """
    Top-level academic subject (e.g., 'Operating Systems', 'Data Structures')
    Defined by teacher, immutable once created
    """
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    units = relationship("Unit", back_populates="subject", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Subject(id={self.id}, name='{self.name}')>"


class Unit(Base):
    """
    Mid-level organizational unit (e.g., 'Memory Management', 'Sorting Algorithms')
    Belongs to exactly one Subject
    Contains multiple Concepts
    """
    __tablename__ = "units"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    order = Column(Integer, default=0, nullable=False)  # Display order within subject
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    subject = relationship("Subject", back_populates="units")
    concepts = relationship("Concept", back_populates="unit", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Unit(id={self.id}, name='{self.name}', subject_id={self.subject_id})>"


class Concept(Base):
    """
    Atomic, examinable knowledge unit (e.g., 'Paging', 'Quick Sort')
    Belongs to exactly one Unit
    This is the finest-grained structure element
    
    diagram_critical: True if this concept requires diagram understanding
    """
    __tablename__ = "concepts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    diagram_critical = Column(Boolean, default=False, nullable=False)
    order = Column(Integer, default=0, nullable=False)  # Display order within unit
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    unit = relationship("Unit", back_populates="concepts")
    aligned_elements = relationship("AlignedElement", back_populates="concept")

    def __repr__(self):
        return f"<Concept(id={self.id}, name='{self.name}', diagram_critical={self.diagram_critical})>"


class AlignedElement(Base):
    """
    Stores alignment of document elements to concepts
    Result of Phase 6: Alignment Engine
    
    alignment_status:
        - ALIGNED: Successfully mapped to concept
        - UNASSIGNED: Low confidence, needs teacher review
    """
    __tablename__ = "aligned_elements"

    id = Column(Integer, primary_key=True, index=True)
    
    # Element data
    element_order = Column(Integer, nullable=False)
    element_type = Column(String(50), nullable=False)
    element_text = Column(Text, nullable=True)
    page_number = Column(Integer, nullable=True)
    
    # Alignment result
    concept_id = Column(Integer, ForeignKey("concepts.id", ondelete="CASCADE"), nullable=True)
    alignment_status = Column(String(20), nullable=False, index=True)  # ALIGNED, UNASSIGNED
    confidence_score = Column(Float, nullable=True)
    
    # Metadata
    source_filename = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    concept = relationship("Concept", back_populates="aligned_elements")
    
    def __repr__(self):
        return f"<AlignedElement(id={self.id}, order={self.element_order}, concept_id={self.concept_id}, status='{self.alignment_status}')>"


class Document(Base):
    """
    Uploaded document metadata
    Tracks document processing status and links to Subject
    """
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(10), nullable=False)  # pdf, pptx, docx
    file_size_bytes = Column(Integer, nullable=False)
    file_path = Column(String(500), nullable=True)  # Path to saved file in uploads/
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    
    # Processing status
    status = Column(String(20), default="pending", nullable=False, index=True)
    # Status values: pending, parsing, parsed, indexed, failed
    
    # Timestamps
    upload_timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    subject = relationship("Subject", backref="documents")
    elements = relationship("ParsedElement", back_populates="document", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', status='{self.status}')>"


class ParsedElement(Base):
    """
    Individual semantic element extracted from a document
    Stores text, metadata, and links to vector DB
    """
    __tablename__ = "parsed_elements"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Element data
    order_index = Column(Integer, nullable=False)  # Position in document
    element_type = Column(String(50), nullable=False)  # Title, NarrativeText, etc.
    category = Column(String(20), nullable=False, index=True)  # TEXT, DIAGRAM, TABLE, CODE, FORMULA
    text = Column(Text, nullable=True)
    page_number = Column(Integer, nullable=True)
    section_path = Column(Text, nullable=True)  # Hierarchy e.g. "Unit II > OSI Model > Layer 3"
    element_metadata = Column(JSON, default={}, nullable=False)  # Renamed from 'metadata' (reserved word)
    
    # Classification
    is_diagram_critical = Column(Boolean, default=False, nullable=False)
    confidence_score = Column(Float, nullable=True)
    
    # Alignment to concepts (optional, set by alignment engine)
    concept_id = Column(Integer, ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True)
    alignment_confidence = Column(Float, nullable=True)
    
    # Vector DB reference
    vector_id = Column(String(100), nullable=True, unique=True)  # Qdrant point ID
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    embedding_model = Column(String(100), nullable=True)  # e.g. all-MiniLM-L6-v2
    embedding_dim = Column(Integer, nullable=True)  # 384
    embedded_at = Column(DateTime(timezone=True), nullable=True)
    
    # Embedding storage (for backup/debugging)
    embedding_vector = Column(JSON, nullable=True)  # 384-dimensional embedding as JSON array
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="elements")
    concept = relationship("Concept", backref="parsed_elements")
    
    def __repr__(self):
        return f"<ParsedElement(id={self.id}, doc_id={self.document_id}, type='{self.element_type}', category='{self.category}')>"


class ParentContext(Base):
    """
    Parent Context - Large contextual units for LLM answer generation.
    Brain Upgrade: Stores 2000-4000 token sections/units as rich context.
    
    Architecture:
    - Parents = full sections (stored in Postgres)
    - Children = 500-token chunks (indexed in Qdrant, linked via parent_id)
    - Search workflow: Query children → retrieve parent → feed to LLM
    """
    __tablename__ = "parent_contexts"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_type = Column(String(50), nullable=False)  # 'section', 'unit', 'chapter', 'subsection'
    parent_index = Column(Integer, nullable=False)  # Order within document (0, 1, 2...)
    
    text = Column(Text, nullable=False)  # Full section text (2000-4000 tokens)
    section_path = Column(Text, nullable=True)  # Section hierarchy
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    source_element_orders = Column(JSON, default=list, nullable=False)
    token_count = Column(Integer, nullable=True)
    
    # Structure alignment
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True)
    concept_id = Column(Integer, ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True)
    alignment_confidence = Column(Float, nullable=True)
    
    # Optional: Parent-level embedding (usually we only embed children)
    embedding_vector = Column(JSON, nullable=True)
    vector_id = Column(String(100), nullable=True, unique=True)
    embedding_model = Column(String(100), nullable=True)  # text-embedding-3-small
    embedding_dim = Column(Integer, nullable=True)  # 1536
    embedded_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    document = relationship("Document", backref=backref("parent_contexts", cascade="all, delete-orphan"))
    unit = relationship("Unit", backref="parent_contexts")
    concept = relationship("Concept", backref="parent_contexts")
    
    def __repr__(self):
        return f"<ParentContext(id={self.id}, doc_id={self.document_id}, type='{self.parent_type}', tokens={self.token_count})>"


class DocumentChunk(Base):
    """
    Child Chunk - Small semantic chunks for precise retrieval.
    Brain Upgrade: 500-token chunks indexed in Qdrant, linked to parent via parent_id.
    
    Architecture:
    - Children (this table) = 500-token chunks for precision search
    - Parents (parent_contexts) = 2000-4000 token sections for LLM context
    - Each child points to parent_id for context retrieval
    """
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)  # Order of chunk within document
    
    # Parent-Child Link (Brain Upgrade)
    parent_id = Column(Integer, ForeignKey("parent_contexts.id", ondelete="CASCADE"), nullable=True, index=True)
    child_order = Column(Integer, nullable=True)  # Order within parent (0, 1, 2...)

    text = Column(Text, nullable=False)
    section_path = Column(Text, nullable=True)  # Section hierarchy; can be long for deep slide decks
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    source_element_orders = Column(JSON, default=list, nullable=False)  # List of ParsedElement order_index
    token_count = Column(Integer, nullable=True)  # Approx tokens for context budgeting (~500)
    chunk_type = Column(String(30), default="text", nullable=False)  # text, table_row, table_schema
    table_id = Column(Integer, nullable=True)  # element order of source table (for table_row/table_schema)
    row_id = Column(Integer, nullable=True)    # 0-based row index (for table_row only)

    unit_id = Column(Integer, ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True)
    concept_id = Column(Integer, ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True)
    alignment_confidence = Column(Float, nullable=True)

    embedding_vector = Column(JSON, nullable=True)
    vector_id = Column(String(100), nullable=True, unique=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    embedding_model = Column(String(100), nullable=True)  # text-embedding-3-small
    embedding_dim = Column(Integer, nullable=True)  # 1536
    embedded_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document = relationship("Document", backref=backref("chunks", cascade="all, delete-orphan"))
    parent = relationship("ParentContext", backref="children")
    unit = relationship("Unit", backref="chunks")
    concept = relationship("Concept", backref="chunks")

    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, doc_id={self.document_id}, chunk_index={self.chunk_index}, parent_id={self.parent_id})>"


class Exam(Base):
    """Generated exam: blueprint, seed, and link to subject."""
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint = Column(JSON, nullable=False)  # unit_ids/concept_ids, counts, difficulty, Bloom, seed
    seed = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    subject = relationship("Subject", backref="exams")
    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan")


class Question(Base):
    """Single question in an exam: type, difficulty, Bloom, text, answer key."""
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(20), nullable=False)  # mcq, short, long
    difficulty = Column(String(20), nullable=True)  # easy, medium, hard
    bloom_level = Column(String(50), nullable=True)
    text = Column(Text, nullable=False)
    options = Column(JSON, nullable=True)  # ["A...", "B...", "C...", "D..."] for MCQs
    explanation = Column(Text, nullable=True)
    answer_key = Column(JSON, nullable=True)  # correct_option, key_points, rubric, etc.
    tags = Column(JSON, default=list, nullable=True)

    exam = relationship("Exam", back_populates="questions")


class QuestionSource(Base):
    """Traceability: which chunk(s) a question was generated from."""
    __tablename__ = "question_sources"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(Integer, ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True, index=True)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)

    question = relationship("Question", backref="sources")
    chunk = relationship("DocumentChunk", backref="question_sources")


# ==========================================
# LAYER 3: QUESTION BANK (concept-centric pipeline)
# ==========================================

class BankQuestion(Base):
    """
    Question in the bank (Layer 3). Tagged with concept/unit/CO/Bloom; source_chunk_ids for traceability.
    status: pending | approved | rejected
    """
    __tablename__ = "question_bank"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True)
    concept_id = Column(Integer, ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True)

    question_text = Column(Text, nullable=False)
    question_type = Column(String(20), nullable=False)  # MCQ, SHORT, LONG, NUMERICAL, DIAGRAM
    marks = Column(Integer, default=1, nullable=False)
    options = Column(JSON, nullable=True)  # ["A...", "B...", ...]
    correct_answer = Column(String(20), nullable=True)  # A/B/C/D or key
    answer_key = Column(JSON, nullable=True)  # rubric, key_points, steps
    explanation = Column(Text, nullable=True)
    bloom_level = Column(String(20), nullable=True)  # BT1–BT6
    difficulty = Column(String(5), nullable=True)  # E, M, H
    co_ids = Column(JSON, default=list, nullable=False)  # [] until CO manager
    source_chunk_ids = Column(JSON, default=list, nullable=False)
    quality_flags = Column(JSON, nullable=True)
    generator_metadata = Column(JSON, nullable=True)

    status = Column(String(20), default="pending", nullable=False, index=True)  # pending | approved | rejected
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    subject = relationship("Subject", backref="bank_questions")
    unit = relationship("Unit", backref="bank_questions")
    concept = relationship("Concept", backref="bank_questions")
    sources = relationship("BankQuestionSource", back_populates="question", cascade="all, delete-orphan")


class BankQuestionSource(Base):
    """Traceability: which chunk(s) this bank question was generated from."""
    __tablename__ = "bank_question_sources"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(Integer, ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True, index=True)

    question = relationship("BankQuestion", back_populates="sources")
    chunk = relationship("DocumentChunk", backref="bank_question_sources")


class QuestionGenerationRun(Base):
    """Tracks each generation run for analytics: acceptance rate, fail reasons."""
    __tablename__ = "question_generation_runs"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True)
    concept_id = Column(Integer, ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True)

    prompt_version = Column(String(50), nullable=True)
    model = Column(String(100), nullable=True)
    status = Column(String(20), default="running", nullable=False, index=True)  # running | completed | failed
    counts_requested = Column(JSON, nullable=True)  # {mcq: 2, short: 1, long: 1}
    counts_accepted = Column(JSON, nullable=True)  # {mcq: 1, short: 1, long: 0}
    fail_reasons = Column(JSON, default=list, nullable=False)  # list of strings
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class QuestionQualityScore(Base):
    """Per-question quality scores from validator (groundedness, ambiguity, duplicate)."""
    __tablename__ = "question_quality_scores"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False, index=True)
    grounded_score = Column(Float, nullable=True)  # 0–1
    ambiguity_score = Column(Float, nullable=True)  # 0 = clear, 1 = ambiguous
    duplicate_score = Column(Float, nullable=True)  # max similarity to existing
    validator_model = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
