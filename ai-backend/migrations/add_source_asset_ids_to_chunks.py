"""
Migration: Phase 3 — add source_asset_ids to document_chunks.

Stores asset IDs linked to each chunk (by source_element_order overlap) so retrieval
can return chunk + figure refs for generation.
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


def _column_exists(conn, table: str, column: str) -> bool:
    r = conn.execute(text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column})
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
        if not _column_exists(conn, "document_chunks", "source_asset_ids"):
            conn.execute(text(
                "ALTER TABLE document_chunks ADD COLUMN source_asset_ids JSONB NOT NULL DEFAULT '[]'::jsonb"
            ))
            conn.commit()
            print("Added document_chunks.source_asset_ids")
        else:
            print("document_chunks.source_asset_ids already exists")

    print("Migration add_source_asset_ids_to_chunks completed.")


if __name__ == "__main__":
    run()
