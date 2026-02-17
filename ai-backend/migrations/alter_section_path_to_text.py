"""
Migration: Alter document_chunks.section_path from VARCHAR(500) to TEXT
Allows long section hierarchies from slide decks.
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


def run_migration():
    POSTGRES_USER = os.getenv("POSTGRES_USER", "academic_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "academic_pass")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "academic_structure")
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

    engine = create_engine(db_url)
    with engine.connect() as conn:
        # Only alter if table and column exist (table may not exist on fresh install)
        r = conn.execute(text("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'document_chunks' AND column_name = 'section_path'
        """)).fetchone()
        if not r:
            print("  (document_chunks.section_path not found, skipping)")
            return
        if r[0] == "text":
            print("  (document_chunks.section_path already TEXT)")
            return
        conn.execute(text("ALTER TABLE document_chunks ALTER COLUMN section_path TYPE TEXT USING section_path::TEXT"))
        conn.commit()
    print("✓ document_chunks.section_path altered to TEXT")


if __name__ == "__main__":
    run_migration()
