"""
Migration: Add academic classification fields to document_chunks table.

New columns:
  chunk_uuid        UUID       — normalized chunk identifier (unique)
  section_type      VARCHAR    — definition | example | derivation | exercise | explanation | summary
  source_type       VARCHAR    — syllabus | lecture_note | textbook | slide
  blooms_level      VARCHAR    — remember | understand | apply | analyze | evaluate | create
  blooms_level_int  INTEGER    — 1–6 (Bloom's numeric for filtering/ordering)
  difficulty        VARCHAR    — easy | medium | hard
  difficulty_score  FLOAT      — 0.0 (trivial) → 1.0 (very hard)
  usage_count       INTEGER    — how often chunk has been used for question generation

BM25 column (already added by add_chunk_search_vector migration):
  search_vector     TSVECTOR   — auto-maintained by DB trigger
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


def _column_exists(conn, table: str, column: str) -> bool:
    r = conn.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = :t AND column_name = :c
    """), {"t": table, "c": column})
    return r.fetchone() is not None


def _index_exists(conn, index_name: str) -> bool:
    r = conn.execute(text("""
        SELECT 1 FROM pg_indexes WHERE indexname = :n
    """), {"n": index_name})
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

        # ── Enable pgcrypto for gen_random_uuid() ──────────────────────────────
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            conn.commit()
        except Exception as e:
            print(f"  pgcrypto extension: {e}")

        # ── chunk_uuid ──────────────────────────────────────────────────────────
        if not _column_exists(conn, "document_chunks", "chunk_uuid"):
            conn.execute(text("""
                ALTER TABLE document_chunks
                ADD COLUMN chunk_uuid UUID DEFAULT gen_random_uuid() UNIQUE
            """))
            conn.commit()
            print("  ✓ chunk_uuid added")
        else:
            print("  · chunk_uuid already exists")

        # ── section_type ────────────────────────────────────────────────────────
        if not _column_exists(conn, "document_chunks", "section_type"):
            conn.execute(text("""
                ALTER TABLE document_chunks
                ADD COLUMN section_type VARCHAR(30)
            """))
            conn.commit()
            print("  ✓ section_type added")
        else:
            print("  · section_type already exists")

        # ── source_type ─────────────────────────────────────────────────────────
        if not _column_exists(conn, "document_chunks", "source_type"):
            conn.execute(text("""
                ALTER TABLE document_chunks
                ADD COLUMN source_type VARCHAR(30)
            """))
            conn.commit()
            print("  ✓ source_type added")
        else:
            print("  · source_type already exists")

        # ── blooms_level ────────────────────────────────────────────────────────
        if not _column_exists(conn, "document_chunks", "blooms_level"):
            conn.execute(text("""
                ALTER TABLE document_chunks
                ADD COLUMN blooms_level VARCHAR(20)
            """))
            conn.commit()
            print("  ✓ blooms_level added")
        else:
            print("  · blooms_level already exists")

        # ── blooms_level_int ────────────────────────────────────────────────────
        if not _column_exists(conn, "document_chunks", "blooms_level_int"):
            conn.execute(text("""
                ALTER TABLE document_chunks
                ADD COLUMN blooms_level_int INTEGER
            """))
            conn.commit()
            print("  ✓ blooms_level_int added")
        else:
            print("  · blooms_level_int already exists")

        # ── difficulty ──────────────────────────────────────────────────────────
        if not _column_exists(conn, "document_chunks", "difficulty"):
            conn.execute(text("""
                ALTER TABLE document_chunks
                ADD COLUMN difficulty VARCHAR(10)
            """))
            conn.commit()
            print("  ✓ difficulty added")
        else:
            print("  · difficulty already exists")

        # ── difficulty_score ────────────────────────────────────────────────────
        if not _column_exists(conn, "document_chunks", "difficulty_score"):
            conn.execute(text("""
                ALTER TABLE document_chunks
                ADD COLUMN difficulty_score FLOAT
            """))
            conn.commit()
            print("  ✓ difficulty_score added")
        else:
            print("  · difficulty_score already exists")

        # ── usage_count ─────────────────────────────────────────────────────────
        if not _column_exists(conn, "document_chunks", "usage_count"):
            conn.execute(text("""
                ALTER TABLE document_chunks
                ADD COLUMN usage_count INTEGER NOT NULL DEFAULT 0
            """))
            conn.commit()
            print("  ✓ usage_count added")
        else:
            print("  · usage_count already exists")

        # ── Indexes ─────────────────────────────────────────────────────────────
        idx_specs = [
            ("idx_dc_blooms_level_int", "CREATE INDEX IF NOT EXISTS idx_dc_blooms_level_int ON document_chunks (blooms_level_int)"),
            ("idx_dc_difficulty",       "CREATE INDEX IF NOT EXISTS idx_dc_difficulty ON document_chunks (difficulty)"),
            ("idx_dc_section_type",     "CREATE INDEX IF NOT EXISTS idx_dc_section_type ON document_chunks (section_type)"),
            ("idx_dc_source_type",      "CREATE INDEX IF NOT EXISTS idx_dc_source_type ON document_chunks (source_type)"),
            ("idx_dc_usage_count",      "CREATE INDEX IF NOT EXISTS idx_dc_usage_count ON document_chunks (usage_count)"),
            ("idx_dc_blooms_level",     "CREATE INDEX IF NOT EXISTS idx_dc_blooms_level ON document_chunks (blooms_level)"),
        ]
        for idx_name, ddl in idx_specs:
            conn.execute(text(ddl))
            conn.commit()
            print(f"  ✓ Index {idx_name} ensured")

        # ── Backfill chunk_uuid for any rows that somehow have NULL ─────────────
        conn.execute(text("""
            UPDATE document_chunks
            SET chunk_uuid = gen_random_uuid()
            WHERE chunk_uuid IS NULL
        """))
        conn.commit()
        print("  ✓ chunk_uuid backfilled for any NULL rows")

    print("\nMigration add_academic_classification_fields completed successfully.")


if __name__ == "__main__":
    run()
