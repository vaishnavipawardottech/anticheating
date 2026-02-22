"""
Database Migration: Brain Upgrade - Parent-Child Architecture
Adds parent_contexts table and parent_id to document_chunks

Run this ONCE after deploying the Brain Upgrade code.

Usage:
    cd ai-backend
    python migrations/brain_upgrade_add_parent_child.py
"""

import sys
import os

# Add parent directory to path so we can import database module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.database import engine, SessionLocal


def run_migration():
    """
    Add parent_contexts table and update document_chunks with parent_id
    """
    print("\n" + "="*70)
    print("BRAIN UPGRADE MIGRATION: Parent-Child Architecture")
    print("="*70)
    
    with engine.connect() as conn:
        # 1. Create parent_contexts table
        print("\n[1/3] Creating parent_contexts table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS parent_contexts (
                id SERIAL PRIMARY KEY,
                document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                parent_type VARCHAR(50) NOT NULL,
                parent_index INTEGER NOT NULL,
                
                text TEXT NOT NULL,
                section_path TEXT,
                page_start INTEGER,
                page_end INTEGER,
                source_element_orders JSONB DEFAULT '[]'::jsonb NOT NULL,
                token_count INTEGER,
                
                unit_id INTEGER REFERENCES units(id) ON DELETE SET NULL,
                concept_id INTEGER REFERENCES concepts(id) ON DELETE SET NULL,
                alignment_confidence REAL,
                
                embedding_vector JSONB,
                vector_id VARCHAR(100) UNIQUE,
                embedding_model VARCHAR(100),
                embedding_dim INTEGER,
                embedded_at TIMESTAMP WITH TIME ZONE,
                
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
            );
        """))
        conn.commit()
        print("   ✓ parent_contexts table created")
        
        # 2. Add indexes to parent_contexts
        print("\n[2/3] Adding indexes to parent_contexts...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_parent_document ON parent_contexts(document_id);",
            "CREATE INDEX IF NOT EXISTS idx_parent_unit ON parent_contexts(unit_id);",
            "CREATE INDEX IF NOT EXISTS idx_parent_concept ON parent_contexts(concept_id);"
        ]
        for idx_sql in indexes:
            conn.execute(text(idx_sql))
        conn.commit()
        print("   ✓ Indexes created")
        
        # 3. Add parent_id and child_order to document_chunks
        print("\n[3/3] Updating document_chunks with parent_id...")
        try:
            conn.execute(text("""
                ALTER TABLE document_chunks
                ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES parent_contexts(id) ON DELETE CASCADE,
                ADD COLUMN IF NOT EXISTS child_order INTEGER;
            """))
            conn.commit()
            print("   ✓ parent_id column added")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("   ✓ parent_id column already exists")
            else:
                raise
        
        # Add index
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_chunk_parent ON document_chunks(parent_id);
        """))
        conn.commit()
        print("   ✓ Index created on parent_id")
    
    print("\n" + "="*70)
    print("MIGRATION COMPLETE")
    print("="*70)
    print("\nNext steps:")
    print("1. Set OPENAI_API_KEY environment variable")
    print("2. Run: python recreate_qdrant_collections.py")
    print("   (This will recreate collections with 1536 dimensions)")
    print("3. Restart your API server")
    print("4. Re-upload documents to populate parent-child structure")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
