"""
Reset the database: drop all tables (public schema) and leave it empty.
Run this before a full migration to start from a clean slate.

Requires Docker Postgres to be running:
  cd ai-backend && docker compose up -d

Usage:
  cd ai-backend && source .venv/bin/activate && python reset_db.py
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


def run():
    POSTGRES_USER = os.getenv("POSTGRES_USER", "academic_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "academic_pass")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "academic_structure")
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    engine = create_engine(db_url)

    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.commit()
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
        conn.commit()
        # So the app user can create tables
        conn.execute(text(f"GRANT ALL ON SCHEMA public TO {POSTGRES_USER}"))
        conn.commit()
    print("Database reset: all tables dropped. Run ./run-migrations.sh to recreate.")


if __name__ == "__main__":
    run()
