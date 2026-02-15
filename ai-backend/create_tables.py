"""
Database migration script
Creates new tables for document processing pipeline
Run this to add Document and ParsedElement tables
"""

from database.database import engine, Base
from database.models import Subject, Unit, Concept, AlignedElement, Document, ParsedElement

def create_tables():
    """Create all tables in the database"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✓ Tables created successfully!")
    print("\nCreated tables:")
    print("  - subjects")
    print("  - units")
    print("  - concepts")
    print("  - aligned_elements")
    print("  - documents (NEW)")
    print("  - parsed_elements (NEW)")

if __name__ == "__main__":
    create_tables()
