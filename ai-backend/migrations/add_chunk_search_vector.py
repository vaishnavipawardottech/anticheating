"""
Migration: Add search_vector (tsvector) to document_chunks for hybrid FTS + vector retrieval.
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


def _column_exists(conn, table: str, column: str):
    r = conn.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = :t AND column_name = :c
    """), {"t": table, "c": column})
    return r.fetchone() is not None


def run():
    POSTGRES_USER = os.getenv("POSTGRES_USER", "academic_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "academic_pass")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "academic_structure")
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    engine = create_engine(db_url)

    with engine.connect() as conn:
        if _column_exists(conn, "document_chunks", "search_vector"):
            print("  document_chunks.search_vector already exists")
        else:
            conn.execute(text("""
                ALTER TABLE document_chunks
                ADD COLUMN search_vector tsvector
            """))
            conn.commit()
            print("  document_chunks.search_vector added")

        # GIN index for fast FTS
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_search_vector
            ON document_chunks USING GIN (search_vector)
        """))
        conn.commit()
        print("  GIN index on search_vector created (or exists)")

        # Backfill: set search_vector from text + section_path (weight path higher for headings)
        conn.execute(text("""
            UPDATE document_chunks
            SET search_vector = (
                setweight(to_tsvector('english', COALESCE(text, '')), 'A')
                || setweight(to_tsvector('english', COALESCE(section_path, '')), 'B')
            )
            WHERE search_vector IS NULL AND (text IS NOT NULL OR section_path IS NOT NULL)
        """))
        conn.commit()
        print("  Backfilled search_vector for existing rows")

        # Trigger to keep search_vector in sync on insert/update
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION document_chunks_search_vector_trigger() RETURNS trigger AS $$
            BEGIN
                NEW.search_vector :=
                    setweight(to_tsvector('english', COALESCE(NEW.text, '')), 'A')
                    || setweight(to_tsvector('english', COALESCE(NEW.section_path, '')), 'B');
                RETURN NEW;
            END
            $$ LANGUAGE plpgsql;
        """))
        conn.commit()
        conn.execute(text("""
            DROP TRIGGER IF EXISTS document_chunks_search_vector_update ON document_chunks;
            CREATE TRIGGER document_chunks_search_vector_update
                BEFORE INSERT OR UPDATE OF text, section_path ON document_chunks
                FOR EACH ROW EXECUTE PROCEDURE document_chunks_search_vector_trigger();
        """))
        conn.commit()
    # PostgreSQL 11+ uses EXECUTE FUNCTION; older uses EXECUTE PROCEDURE
    # If trigger creation fails, try: EXECUTE PROCEDURE
    print("✓ Migration add_chunk_search_vector completed")


if __name__ == "__main__":
    run()
