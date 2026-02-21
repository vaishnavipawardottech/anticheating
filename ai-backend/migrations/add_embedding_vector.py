"""
Migration: Add embedding_vector (JSONB) to parsed_elements for backup/debugging.
Idempotent: skips if column already exists.
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


def run():
    POSTGRES_USER = os.getenv("POSTGRES_USER", "academic_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "academic_pass")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "academic_structure")
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    engine = create_engine(db_url)

    with engine.connect() as conn:
        if _column_exists(conn, "parsed_elements", "embedding_vector"):
            print("  parsed_elements.embedding_vector already exists")
        else:
            conn.execute(text("""
                ALTER TABLE parsed_elements
                ADD COLUMN embedding_vector JSONB
            """))
            conn.commit()
            print("  parsed_elements.embedding_vector added")

    print("Migration add_embedding_vector completed")


if __name__ == "__main__":
    run()
