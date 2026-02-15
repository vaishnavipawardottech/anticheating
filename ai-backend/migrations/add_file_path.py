"""
Migration: Add file_path column to documents table
Adds permanent file storage path tracking
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    """Add file_path column to documents table"""
    
    # Build database URL from environment variables
    POSTGRES_USER = os.getenv("POSTGRES_USER", "academic_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "academic_pass")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "academic_structure")
    
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    engine = create_engine(db_url)
    
    print("=" * 60)
    print("RUNNING MIGRATION: Add file_path column")
    print("=" * 60)
    
    with engine.connect() as conn:
        # Check if column already exists
        check_sql = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'documents' 
            AND column_name = 'file_path'
        """)
        
        result = conn.execute(check_sql)
        if result.fetchone():
            print("Column 'file_path' already exists in documents table")
            print("\nMigration complete!")
            return
        
        # Add file_path column
        print("Adding file_path column to documents table...")
        alter_sql = text("""
            ALTER TABLE documents 
            ADD COLUMN file_path VARCHAR(500)
        """)
        
        conn.execute(alter_sql)
        conn.commit()
        
        print("✓ Added file_path column")
        print("\nMigration complete!")


def rollback_migration():
    """Remove file_path column (rollback)"""
    
    # Build database URL
    POSTGRES_USER = os.getenv("POSTGRES_USER", "academic_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "academic_pass")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "academic_structure")
    
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    engine = create_engine(db_url)
    
    print("=" * 60)
    print("ROLLING BACK: Remove file_path column")
    print("=" * 60)
    
    with engine.connect() as conn:
        rollback_sql = text("""
            ALTER TABLE documents 
            DROP COLUMN IF EXISTS file_path
        """)
        
        conn.execute(rollback_sql)
        conn.commit()
        
        print("✓ Removed file_path column")
        print("\nRollback complete!")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback_migration()
    else:
        run_migration()
