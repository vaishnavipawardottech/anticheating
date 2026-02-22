"""
Migration: Ensure section_path is TEXT type on parsed_elements and document_chunks.
Idempotent: no-op if column is already TEXT (e.g. created by current create_tables).
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


def _column_type(conn, table: str, column: str) -> str | None:
    r = conn.execute(text("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = :t AND column_name = :c
    """), {"t": table, "c": column})
    row = r.fetchone()
    return row[0] if row else None


def run():
    POSTGRES_USER = os.getenv("POSTGRES_USER", "academic_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "academic_pass")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "academic_structure")
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    engine = create_engine(db_url)

    with engine.connect() as conn:
        for table in ("parsed_elements", "document_chunks"):
            dt = _column_type(conn, table, "section_path")
            if dt is None:
                print(f"  {table}.section_path does not exist (skip)")
            elif dt == "text":
                print(f"  {table}.section_path already TEXT")
            else:
                conn.execute(text(f"""
                    ALTER TABLE {table}
                    ALTER COLUMN section_path TYPE TEXT
                """))
                conn.commit()
                print(f"  {table}.section_path altered to TEXT")

    print("Migration alter_section_path_to_text completed")


if __name__ == "__main__":
    run()
