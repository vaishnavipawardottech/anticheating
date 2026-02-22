"""
Migration: Add paper_type column to generated_papers table

This migration:
1. Adds paper_type ENUM type to PostgreSQL
2. Adds paper_type column to generated_papers table
3. Infers paper_type from existing papers by checking question types
4. Sets default to 'subjective' for any ambiguous cases
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from database.database import engine, SessionLocal
from database.models import GeneratedPaper


def infer_paper_type(paper_json: dict) -> str:
    """
    Infer paper type from paper_json by checking question types.
    Returns 'mcq' if all questions are MCQ, 'subjective' otherwise.
    """
    sections = paper_json.get('sections', [])
    
    if not sections:
        return 'subjective'  # Default for empty papers
    
    all_mcq = True
    has_questions = False
    
    for section in sections:
        variants = section.get('variants', [])
        for variant in variants:
            question = variant.get('question', {})
            question_type = question.get('question_type', 'descriptive')
            has_questions = True
            
            if question_type != 'mcq':
                all_mcq = False
                break
        
        if not all_mcq:
            break
    
    if not has_questions:
        return 'subjective'
    
    return 'mcq' if all_mcq else 'subjective'


def migrate():
    """Run the migration"""
    print("=" * 80)
    print("Migration: Add paper_type to generated_papers")
    print("=" * 80)
    
    with engine.connect() as conn:
        # Step 1: Create ENUM type if it doesn't exist
        print("\n[1/4] Creating paper_type ENUM type...")
        try:
            conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE papertype AS ENUM ('mcq', 'subjective');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            conn.commit()
            print("✓ ENUM type created/verified")
        except Exception as e:
            print(f"⚠ ENUM creation warning: {e}")
            conn.rollback()
        
        # Step 2: Add paper_type column with default
        print("\n[2/4] Adding paper_type column...")
        try:
            conn.execute(text("""
                ALTER TABLE generated_papers 
                ADD COLUMN IF NOT EXISTS paper_type papertype DEFAULT 'subjective';
            """))
            conn.commit()
            print("✓ Column added")
        except Exception as e:
            print(f"✗ Failed to add column: {e}")
            return False
        
        # Step 3: Create index
        print("\n[3/4] Creating index on paper_type...")
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_generated_papers_paper_type 
                ON generated_papers(paper_type);
            """))
            conn.commit()
            print("✓ Index created")
        except Exception as e:
            print(f"⚠ Index warning: {e}")
            conn.rollback()
    
    # Step 4: Infer and update paper types for existing papers
    print("\n[4/4] Inferring paper types from existing papers...")
    
    with engine.connect() as conn:
        # Get all papers using raw SQL
        result = conn.execute(text("SELECT id, paper_json FROM generated_papers"))
        papers = [(row[0], row[1]) for row in result]
        print(f"Found {len(papers)} existing papers")
        
        mcq_count = 0
        subjective_count = 0
        
        for paper_id, paper_json in papers:
            inferred_type = infer_paper_type(paper_json)
            
            # Update paper_type in database
            conn.execute(
                text("UPDATE generated_papers SET paper_type = :ptype WHERE id = :pid"),
                {"ptype": inferred_type, "pid": paper_id}
            )
            
            if inferred_type == 'mcq':
                mcq_count += 1
            else:
                subjective_count += 1
            
            print(f"  Paper {paper_id}: {inferred_type}")
        
        conn.commit()
        
        print(f"\n✓ Updated {len(papers)} papers:")
        print(f"  - MCQ: {mcq_count}")
        print(f"  - Subjective: {subjective_count}")
    
    print("\n" + "=" * 80)
    print("✅ Migration completed successfully!")
    print("=" * 80)
    return True


def rollback():
    """Rollback the migration"""
    print("=" * 80)
    print("Rollback: Remove paper_type from generated_papers")
    print("=" * 80)
    
    with engine.connect() as conn:
        try:
            # Drop index
            print("\n[1/3] Dropping index...")
            conn.execute(text("DROP INDEX IF EXISTS ix_generated_papers_paper_type;"))
            conn.commit()
            print("✓ Index dropped")
            
            # Drop column
            print("\n[2/3] Dropping paper_type column...")
            conn.execute(text("ALTER TABLE generated_papers DROP COLUMN IF EXISTS paper_type;"))
            conn.commit()
            print("✓ Column dropped")
            
            # Drop ENUM (optional - might be used elsewhere)
            print("\n[3/3] Dropping ENUM type...")
            conn.execute(text("DROP TYPE IF EXISTS papertype;"))
            conn.commit()
            print("✓ ENUM dropped")
            
        except Exception as e:
            print(f"✗ Rollback failed: {e}")
            conn.rollback()
            return False
    
    print("\n" + "=" * 80)
    print("✅ Rollback completed!")
    print("=" * 80)
    return True


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
