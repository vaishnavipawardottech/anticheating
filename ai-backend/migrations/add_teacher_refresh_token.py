"""
Migration: Add refresh_token column to teachers.
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
        if _column_exists(conn, "teachers", "refresh_token"):
            print("  teachers.refresh_token already exists")
        else:
            conn.execute(text("""
                ALTER TABLE teachers
                ADD COLUMN refresh_token VARCHAR(512) NULL
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_teachers_refresh_token
                ON teachers (refresh_token)
            """))
            conn.commit()
            print("  teachers.refresh_token added")
    print("Migration add_teacher_refresh_token done.")


if __name__ == "__main__":
    run()
