"""
Migration: Add teacher_id column to generated_papers.
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
        if _column_exists(conn, "generated_papers", "teacher_id"):
            print("  generated_papers.teacher_id already exists")
        else:
            conn.execute(text("""
                ALTER TABLE generated_papers
                ADD COLUMN teacher_id INTEGER NULL
                REFERENCES teachers(id) ON DELETE SET NULL
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_generated_papers_teacher_id
                ON generated_papers(teacher_id)
            """))
            conn.commit()
            print("  generated_papers.teacher_id added")
    print("Migration add_generated_papers_teacher_id done.")


if __name__ == "__main__":
    run()
