"""
Database migration script
Creates new tables for document processing pipeline
Run this to add Document and ParsedElement tables
"""

from database.database import engine, Base
from database.models import (
    Subject, Unit, Concept, AlignedElement,
    Document, ParsedElement, DocumentChunk,
    Exam, Question, QuestionSource,
    BankQuestion, BankQuestionSource, QuestionGenerationRun, QuestionQualityScore,
)

def create_tables():
    """Create all tables in the database"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")
    print("\nCreated tables:")
    print("  - subjects, units, concepts, aligned_elements")
    print("  - documents, parsed_elements, document_chunks")
    print("  - exams, questions, question_sources")

if __name__ == "__main__":
    create_tables()
