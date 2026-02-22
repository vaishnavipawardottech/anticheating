"""
Migration: Add visual_chunks table and source_asset_ids on question_bank.

visual_chunks: diagram/table/equation assets per page, with caption and Qdrant index.
source_asset_ids: list of VisualChunk IDs for questions that include a figure.
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


def _table_exists(conn, table: str) -> bool:
    r = conn.execute(text("""
        SELECT 1 FROM information_schema.tables WHERE table_name = :t
    """), {"t": table})
    return r.fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
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
        # ── visual_chunks table ───────────────────────────────────────────────────
        if not _table_exists(conn, "visual_chunks"):
            create_sql = (
                "CREATE TABLE visual_chunks ("
                "id SERIAL PRIMARY KEY, "
                "document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE, "
                "page_no INTEGER NOT NULL, "
                "asset_type VARCHAR(20) NOT NULL, "
                "image_path VARCHAR(500) NOT NULL, "
                "caption_text TEXT, ocr_text TEXT, structured_json JSONB, "
                "concept_id INTEGER REFERENCES concepts(id) ON DELETE SET NULL, "
                "unit_id INTEGER REFERENCES units(id) ON DELETE SET NULL, "
                "alignment_confidence FLOAT, usage_count INTEGER NOT NULL DEFAULT 0, "
                "embedding_vector JSONB, vector_id VARCHAR(100) UNIQUE, "
                "indexed_at TIMESTAMP WITH TIME ZONE, embedding_model VARCHAR(100), "
                "embedding_dim INTEGER, embedded_at TIMESTAMP WITH TIME ZONE, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
                ")"
            )
            conn.execute(text(create_sql))
            conn.execute(text("CREATE INDEX ix_visual_chunks_document_id ON visual_chunks(document_id)"))
            conn.execute(text("CREATE INDEX ix_visual_chunks_page_no ON visual_chunks(page_no)"))
            conn.execute(text("CREATE INDEX ix_visual_chunks_asset_type ON visual_chunks(asset_type)"))
            conn.execute(text("CREATE INDEX ix_visual_chunks_concept_id ON visual_chunks(concept_id)"))
            conn.execute(text("CREATE INDEX ix_visual_chunks_unit_id ON visual_chunks(unit_id)"))
            conn.commit()
            print("Created table visual_chunks and indexes")
        else:
            print("Table visual_chunks already exists")

        # ── source_asset_ids on question_bank ────────────────────────────────────
        if not _column_exists(conn, "question_bank", "source_asset_ids"):
            conn.execute(text("""
                ALTER TABLE question_bank
                ADD COLUMN source_asset_ids JSONB NOT NULL DEFAULT '[]'
            """))
            conn.commit()
            print("Added question_bank.source_asset_ids")
        else:
            print("question_bank.source_asset_ids already exists")

    print("Migration add_visual_chunks completed.")


if __name__ == "__main__":
    run()
