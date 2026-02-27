"""
SQLAlchemy models for structure truth layer
Subject → Unit → Concept hierarchy

These models are the SOURCE OF TRUTH for academic structure.
NO document references, NO embeddings, NO vectors here.
"""

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Float, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR, JSONB
import uuid
import enum
from database.database import Base


class PaperType(str, enum.Enum):
    """Enum for paper types"""
    MCQ = "mcq"
    SUBJECTIVE = "subjective"


# ==========================================
# AUTH: TEACHERS
# ==========================================

class Teacher(Base):
    """
    Teacher user account for authentication.
    email + hashed_password for login; is_admin grants management access.
    refresh_token stored after login, cleared on logout (for server-side revocation).
    """
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    refresh_token = Column(String(512), nullable=True, index=True)  # set on login, cleared on logout

    def __repr__(self):
        return f"<Teacher(id={self.id}, email='{self.email}', is_admin={self.is_admin})>"


class PaperShare(Base):
    """
    Tracks sharing of a GeneratedPaper from one teacher to another.
    A teacher can share any paper with any other teacher.
    """
    __tablename__ = "paper_shares"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("generated_papers.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_by_id = Column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_with_id = Column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    shared_by = relationship("Teacher", foreign_keys=[shared_by_id])
    shared_with = relationship("Teacher", foreign_keys=[shared_with_id])

    def __repr__(self):
        return f"<PaperShare(paper_id={self.paper_id}, from={self.shared_by_id}, to={self.shared_with_id})>"


# ==========================================
# LOOKUP TABLES: DEPARTMENT, DIVISION, YEAR
# ==========================================

class Department(Base):
    """Academic department (e.g. 'Computer Science', 'Information Technology')."""
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    students = relationship("Student", back_populates="department")

    def __repr__(self):
        return f"<Department(id={self.id}, name='{self.name}')>"


class Division(Base):
    """Class division (e.g. 'A', 'B', 'C')."""
    __tablename__ = "divisions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(10), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    students = relationship("Student", back_populates="division")

    def __repr__(self):
        return f"<Division(id={self.id}, name='{self.name}')>"


class YearOfStudy(Base):
    """Year of study (1–4 with label like FE, SE, TE, BE)."""
    __tablename__ = "years_of_study"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, unique=True, nullable=False, index=True)  # 1,2,3,4
    label = Column(String(10), nullable=False)  # FE, SE, TE, BE
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    students = relationship("Student", back_populates="year_of_study")

    def __repr__(self):
        return f"<YearOfStudy(id={self.id}, year={self.year}, label='{self.label}')>"


# ==========================================
# AUTH: STUDENTS
# ==========================================

class Student(Base):
    """Student user account for MCQ exam system."""
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    year_id = Column(Integer, ForeignKey("years_of_study.id", ondelete="SET NULL"), nullable=True, index=True)
    division_id = Column(Integer, ForeignKey("divisions.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    refresh_token = Column(String(512), nullable=True, index=True)
    face_photo_url = Column(String(500), nullable=True)  # Path to uploaded face photo
    face_embedding = Column(JSONB, nullable=True)  # 512-dim ArcFace embedding for face verification
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    department = relationship("Department", back_populates="students")
    year_of_study = relationship("YearOfStudy", back_populates="students")
    division = relationship("Division", back_populates="students")

    def __repr__(self):
        return f"<Student(id={self.id}, email='{self.email}')>"


# ==========================================
# STRUCTURE: SUBJECT → UNIT → CONCEPT
# ==========================================

class Subject(Base):
    """
    Top-level academic subject (e.g., 'Operating Systems', 'Discrete Mathematics').
    Defined by teacher, immutable once created.
    math_mode: when True, enable asset extraction + selective vision + formula-aware chunking (e.g. DM).
    formula_mode: preserve and detect formula/math elements.
    vision_budget: max number of "meaningful" figures to send to vision per document (e.g. 15–25); null = no cap.
    """
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    # Math/visual subject config (Phase 1)
    math_mode = Column(Boolean, default=False, nullable=False, server_default="false")
    formula_mode = Column(Boolean, default=False, nullable=False, server_default="false")
    vision_budget = Column(Integer, nullable=True)  # max figures to vision per doc; null = use default/no hard cap
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
    assets = relationship("Asset", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', status='{self.status}')>"


class Asset(Base):
    """
    Extracted non-text asset from a document: image, table, or page snapshot.
    Used for math_mode ingestion: store every figure/table; optionally enrich with vision (caption, kind, structured_json).
    bbox: optional bounding box {x0, y0, x1, y1} or points from parser coordinates.
    sha256: content hash for dedupe and skip re-captioning.
    kind: set by vision enrichment: weighted_graph | unweighted_graph | tree | truth_table | venn | equation | diagram_other.
    structured_json: graph_json, tree_json, table_md, latex from vision (extract once, reuse at generation).
    """
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_no = Column(Integer, nullable=False)
    bbox = Column(JSON, nullable=True)  # {x0,y0,x1,y1} or points list from parser
    sha256 = Column(String(64), nullable=True, index=True)  # content hash for dedupe
    asset_url = Column(String(500), nullable=False)  # local path (uploads/assets/...) or S3/MinIO URL
    asset_type = Column(String(20), nullable=False, index=True)  # image | table | page_preview
    source_element_order = Column(Integer, nullable=True)  # link to ParsedElement.order_index if from element
    # Vision enrichment (filled when math_mode + selected for vision)
    kind = Column(String(30), nullable=True, index=True)  # weighted_graph | tree | truth_table | equation | diagram_other
    caption = Column(Text, nullable=True)
    structured_json = Column(JSON, nullable=True)  # graph_json, tree_json, table_md, latex
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document = relationship("Document", back_populates="assets")

    def __repr__(self):
        return f"<Asset(id={self.id}, doc_id={self.document_id}, page={self.page_no}, type={self.asset_type}, kind={self.kind})>"


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


class VisualChunk(Base):
    """
    Visual asset from a document page/slide: diagram, table, equation, graph, tree.
    Stored alongside text chunks; caption embedded in Qdrant for retrieval.
    Images stored on disk (uploads/visuals/) or MinIO/S3 path in image_path.
    """
    __tablename__ = "visual_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_no = Column(Integer, nullable=False)  # 1-based page/slide number
    asset_type = Column(String(20), nullable=False, index=True)  # DIAGRAM | TABLE | EQUATION | GRAPH | TREE
    image_path = Column(String(500), nullable=False)  # Path in uploads/visuals/ or MinIO/S3
    caption_text = Column(Text, nullable=True)  # LLM vision summary
    ocr_text = Column(Text, nullable=True)
    structured_json = Column(JSON, nullable=True)  # For graphs/trees: nodes, edges, etc.
    concept_id = Column(Integer, ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True)
    alignment_confidence = Column(Float, nullable=True)
    usage_count = Column(Integer, default=0, nullable=False, server_default="0")
    # Vector index (same as chunks)
    embedding_vector = Column(JSON, nullable=True)
    vector_id = Column(String(100), nullable=True, unique=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    embedding_dim = Column(Integer, nullable=True)
    embedded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document = relationship("Document", backref=backref("visual_chunks", cascade="all, delete-orphan"))
    concept = relationship("Concept", backref="visual_chunks")
    unit = relationship("Unit", backref="visual_chunks")

    def __repr__(self):
        return f"<VisualChunk(id={self.id}, doc_id={self.document_id}, page={self.page_no}, type={self.asset_type})>"


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
    chunk_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=True, index=True)
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
    source_asset_ids = Column(JSON, default=list, nullable=False)  # Phase 3: Asset IDs linked to this chunk (by element overlap)
    token_count = Column(Integer, nullable=True)  # Approx tokens for context budgeting (~500)
    chunk_type = Column(String(30), default="text", nullable=False)  # text, table_row, table_schema
    table_id = Column(Integer, nullable=True)  # element order of source table (for table_row/table_schema)
    row_id = Column(Integer, nullable=True)    # 0-based row index (for table_row only)

    # ─── Step 7: LLM Academic Classification ─────────────────────────────────
    # section_type: what kind of academic content this chunk contains
    section_type = Column(String(30), nullable=True, index=True)
    # values: definition | example | derivation | exercise | explanation | summary

    # source_type: what kind of source material this chunk comes from
    source_type = Column(String(30), nullable=True, index=True)
    # values: syllabus | lecture_note | textbook | slide

    # Bloom's Taxonomy level (keyword + integer for filtering)
    blooms_level = Column(String(20), nullable=True, index=True)
    # values: remember | understand | apply | analyze | evaluate | create
    blooms_level_int = Column(Integer, nullable=True, index=True)
    # values: 1=remember, 2=understand, 3=apply, 4=analyze, 5=evaluate, 6=create

    # Difficulty classification
    difficulty = Column(String(10), nullable=True, index=True)
    # values: easy | medium | hard
    difficulty_score = Column(Float, nullable=True)
    # 0.0 (trivial) → 1.0 (very hard)

    # Usage tracking: how many times this chunk has been used for question generation
    usage_count = Column(Integer, default=0, nullable=False, server_default="0")

    # ─── Step 8: BM25 Full-Text Search ───────────────────────────────────────
    # Populated automatically by DB trigger (see migration add_chunk_search_vector.py)
    # Declared here for ORM awareness; do NOT write to this column manually.
    search_vector = Column(TSVECTOR, nullable=True)
    # ─────────────────────────────────────────────────────────────────────────

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
    source_asset_ids = Column(JSON, default=list, nullable=False)  # VisualChunk IDs for diagram questions
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


# ==========================================
# LAYER 4: GENERATED PAPERS (pattern-based pipeline)
# ==========================================

class GeneratedPaper(Base):
    """
    A complete generated question paper produced by the pattern-based pipeline.
    Stores the full paper JSON, plus metadata for listing and retrieval.
    """
    __tablename__ = "generated_papers"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    paper_type = Column(SQLEnum(PaperType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=PaperType.SUBJECTIVE, index=True)
    pattern_text = Column(Text, nullable=True)   # Raw pattern text (or PDF reference)
    total_marks = Column(Integer, nullable=False)
    paper_json = Column(JSON, nullable=False)     # Full PaperOutput serialised

    # Teacher who created this paper (nullable for backward compatibility with existing papers)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finalised = Column(Boolean, default=False, nullable=False, server_default="false")

    subject = relationship(
        "Subject",
        backref=backref("generated_papers", cascade="all, delete-orphan"),
    )
    teacher = relationship("Teacher", foreign_keys=[teacher_id])
    shares = relationship("PaperShare", foreign_keys="PaperShare.paper_id", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<GeneratedPaper(id={self.id}, subject_id={self.subject_id}, marks={self.total_marks})>"


# ==========================================
# LAYER 5: MCQ POOL & EXAMINATION SYSTEM
# ==========================================

class McqPoolQuestion(Base):
    """
    MCQ question in the pool. Can be AI-generated from ingested docs or manually added by teacher.
    Tagged with unit, bloom's level, and difficulty for filtering.
    """
    __tablename__ = "mcq_pool_questions"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True)
    question_text = Column(Text, nullable=False)
    options = Column(JSON, nullable=False)  # [{"label":"A","text":"..."},{"label":"B","text":"..."},...]
    correct_answer = Column(String(5), nullable=False)  # "A", "B", "C", "D"
    explanation = Column(Text, nullable=True)
    blooms_level = Column(String(20), nullable=True, index=True)  # remember, understand, apply, analyze, evaluate, create
    difficulty = Column(String(10), nullable=True, index=True)  # easy, medium, hard
    created_by = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    subject = relationship("Subject", backref="pool_questions")
    unit = relationship("Unit", backref="pool_questions")
    teacher = relationship("Teacher", foreign_keys=[created_by])

    def __repr__(self):
        return f"<McqPoolQuestion(id={self.id}, subject_id={self.subject_id}, unit_id={self.unit_id})>"


class McqExam(Base):
    """
    MCQ examination created by a teacher.
    exam_mode: 'static' = fixed paper for all students, 'dynamic' = random subset per student.
    """
    __tablename__ = "mcq_exams"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, index=True)
    exam_mode = Column(String(10), nullable=False, default="static")  # 'static' or 'dynamic'
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, nullable=False)  # how long each student gets
    total_questions = Column(Integer, nullable=False)  # for dynamic: how many random Qs to pick
    show_result_to_student = Column(Boolean, default=False, nullable=False, server_default="false")
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    subject = relationship("Subject", backref="mcq_exams")
    teacher = relationship("Teacher", foreign_keys=[created_by])
    questions = relationship("McqExamQuestion", back_populates="exam", cascade="all, delete-orphan")
    assignments = relationship("McqExamAssignment", back_populates="exam", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<McqExam(id={self.id}, title='{self.title}', mode='{self.exam_mode}')>"


class McqExamQuestion(Base):
    """
    Links pool questions to an exam.
    For static mode: defines exact question order.
    For dynamic mode: defines the eligible pool of questions to randomize from.
    """
    __tablename__ = "mcq_exam_questions"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("mcq_exams.id", ondelete="CASCADE"), nullable=False, index=True)
    pool_question_id = Column(Integer, ForeignKey("mcq_pool_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    question_order = Column(Integer, nullable=False)

    exam = relationship("McqExam", back_populates="questions")
    pool_question = relationship("McqPoolQuestion")

    def __repr__(self):
        return f"<McqExamQuestion(exam_id={self.exam_id}, pool_q_id={self.pool_question_id}, order={self.question_order})>"


class McqExamAssignment(Base):
    """Assigns an exam to a specific dept + year + division combination."""
    __tablename__ = "mcq_exam_assignments"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("mcq_exams.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True)
    year_id = Column(Integer, ForeignKey("years_of_study.id", ondelete="CASCADE"), nullable=False, index=True)
    division_id = Column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    exam = relationship("McqExam", back_populates="assignments")
    department = relationship("Department")
    year_of_study = relationship("YearOfStudy")
    division = relationship("Division")

    def __repr__(self):
        return f"<McqExamAssignment(exam_id={self.exam_id}, dept={self.department_id}, year={self.year_id}, div={self.division_id})>"


class McqStudentExamInstance(Base):
    """
    Per-student exam instance. Tracks which questions they got (especially for dynamic mode),
    when they started, and their submission status.
    """
    __tablename__ = "mcq_student_exam_instances"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("mcq_exams.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    questions_order = Column(JSON, nullable=False)  # list of pool_question_ids assigned to this student
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    is_auto_submitted = Column(Boolean, default=False, nullable=False)
    score = Column(Integer, nullable=True)
    total_questions = Column(Integer, nullable=False)

    exam = relationship("McqExam")
    student = relationship("Student")
    responses = relationship("McqStudentResponse", back_populates="instance", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<McqStudentExamInstance(exam_id={self.exam_id}, student_id={self.student_id}, score={self.score})>"


class McqStudentResponse(Base):
    """Individual answer for one question within a student's exam instance."""
    __tablename__ = "mcq_student_responses"

    id = Column(Integer, primary_key=True, index=True)
    instance_id = Column(Integer, ForeignKey("mcq_student_exam_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    pool_question_id = Column(Integer, ForeignKey("mcq_pool_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    selected_option = Column(String(5), nullable=True)  # "A", "B", "C", "D" or null if unanswered
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    instance = relationship("McqStudentExamInstance", back_populates="responses")
    pool_question = relationship("McqPoolQuestion")

    def __repr__(self):
        return f"<McqStudentResponse(instance_id={self.instance_id}, q_id={self.pool_question_id}, ans='{self.selected_option}')>"


# ==========================================
# PROCTORING EVENTS
# ==========================================

class ProctoringEvent(Base):
    """Proctoring event logged during an exam session."""
    __tablename__ = "proctoring_events"

    id = Column(Integer, primary_key=True, index=True)
    instance_id = Column(Integer, ForeignKey("mcq_student_exam_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # TAB_SWITCH, FULLSCREEN_EXIT, MULTIPLE_FACES, etc.
    details = Column(Text, nullable=True)
    snapshot_url = Column(String(500), nullable=True)  # Path to snapshot image
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    instance = relationship("McqStudentExamInstance", backref="proctoring_events")
    student = relationship("Student", backref="proctoring_events")

    def __repr__(self):
        return f"<ProctoringEvent(id={self.id}, instance_id={self.instance_id}, type='{self.event_type}')>"

