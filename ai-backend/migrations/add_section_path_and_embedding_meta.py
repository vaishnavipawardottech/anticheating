"""
Migration: Add section_path and embedding metadata to parsed_elements and document_chunks.

- parsed_elements: section_path (TEXT), embedding_model (VARCHAR), embedding_dim (INT), embedded_at (TIMESTAMPTZ)
- document_chunks: token_count (INT), chunk_type (VARCHAR), embedding_model, embedding_dim, embedded_at
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
        # parsed_elements
        for col, sql in [
            ("section_path", "ALTER TABLE parsed_elements ADD COLUMN section_path TEXT"),
            ("embedding_model", "ALTER TABLE parsed_elements ADD COLUMN embedding_model VARCHAR(100)"),
            ("embedding_dim", "ALTER TABLE parsed_elements ADD COLUMN embedding_dim INTEGER"),
            ("embedded_at", "ALTER TABLE parsed_elements ADD COLUMN embedded_at TIMESTAMPTZ"),
        ]:
            if _column_exists(conn, "parsed_elements", col):
                print(f"  parsed_elements.{col} already exists")
            else:
                conn.execute(text(sql))
                conn.commit()
                print(f"  parsed_elements.{col} added")

        # document_chunks
        for col, sql in [
            ("token_count", "ALTER TABLE document_chunks ADD COLUMN token_count INTEGER"),
            ("chunk_type", "ALTER TABLE document_chunks ADD COLUMN chunk_type VARCHAR(30) DEFAULT 'text' NOT NULL"),
            ("table_id", "ALTER TABLE document_chunks ADD COLUMN table_id INTEGER"),
            ("row_id", "ALTER TABLE document_chunks ADD COLUMN row_id INTEGER"),
            ("embedding_model", "ALTER TABLE document_chunks ADD COLUMN embedding_model VARCHAR(100)"),
            ("embedding_dim", "ALTER TABLE document_chunks ADD COLUMN embedding_dim INTEGER"),
            ("embedded_at", "ALTER TABLE document_chunks ADD COLUMN embedded_at TIMESTAMPTZ"),
        ]:
            if _column_exists(conn, "document_chunks", col):
                print(f"  document_chunks.{col} already exists")
            else:
                conn.execute(text(sql))
                conn.commit()
                print(f"  document_chunks.{col} added")

    print("✓ Migration add_section_path_and_embedding_meta completed")


if __name__ == "__main__":
    run()
