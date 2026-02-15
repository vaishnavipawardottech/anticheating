"""
Migration: Add embedding_vector column to parsed_elements table
Adds JSON field to store 384-dimensional embeddings
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    """Add embedding_vector column to parsed_elements table"""
    
    # Build database URL from environment variables (same as database.py)
    POSTGRES_USER = os.getenv("POSTGRES_USER", "academic_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "academic_pass")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "academic_structure")
    
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    print(f"Connecting to database...")
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # Check if column already exists
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'parsed_elements' 
            AND column_name = 'embedding_vector'
        """)
        
        result = conn.execute(check_query)
        exists = result.fetchone() is not None
        
        if exists:
            print("Column 'embedding_vector' already exists in parsed_elements table")
            return
        
        # Add the column
        print("Adding 'embedding_vector' column to parsed_elements table...")
        alter_query = text("""
            ALTER TABLE parsed_elements 
            ADD COLUMN embedding_vector JSON NULL
        """)
        
        conn.execute(alter_query)
        conn.commit()
        
        print("Successfully added 'embedding_vector' column")
        print("  - Type: JSON")
        print("  - Nullable: True")
        print("  - Purpose: Store 384-dimensional embeddings")

def rollback_migration():
    """Remove embedding_vector column (rollback)"""
    
    # Build database URL from environment variables (same as database.py)
    POSTGRES_USER = os.getenv("POSTGRES_USER", "academic_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "academic_pass")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "academic_structure")
    
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    print(f"Connecting to database...")
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        print("Removing 'embedding_vector' column from parsed_elements table...")
        alter_query = text("""
            ALTER TABLE parsed_elements 
            DROP COLUMN IF EXISTS embedding_vector
        """)
        
        conn.execute(alter_query)
        conn.commit()
        
        print("Successfully removed 'embedding_vector' column")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        print("=" * 60)
        print("ROLLING BACK MIGRATION: Remove embedding_vector column")
        print("=" * 60)
        rollback_migration()
    else:
        print("=" * 60)
        print("RUNNING MIGRATION: Add embedding_vector column")
        print("=" * 60)
        run_migration()
    
    print("\nMigration complete!")
