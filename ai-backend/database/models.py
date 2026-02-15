"""
SQLAlchemy models for structure truth layer
Subject → Unit → Concept hierarchy

These models are the SOURCE OF TRUTH for academic structure.
NO document references, NO embeddings, NO vectors here.
"""

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Float, JSON
from sqlalchemy.orm import relationship
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
    
    # Embedding storage (for backup/debugging)
    embedding_vector = Column(JSON, nullable=True)  # 384-dimensional embedding as JSON array
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="elements")
    concept = relationship("Concept", backref="parsed_elements")
    
    def __repr__(self):
        return f"<ParsedElement(id={self.id}, doc_id={self.document_id}, type='{self.element_type}', category='{self.category}')>"
