"""
Migration: Assign all generated_papers with NULL teacher_id to admin (admin@org.com).
Run once after adding teacher_id column.
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
        r = conn.execute(text("SELECT id FROM teachers WHERE email = 'admin@org.com' LIMIT 1"))
        row = r.fetchone()
        if not row:
            print("  No admin@org.com found; skip assigning papers")
            return
        admin_id = row[0]
        r2 = conn.execute(
            text("UPDATE generated_papers SET teacher_id = :aid WHERE teacher_id IS NULL"),
            {"aid": admin_id},
        )
        conn.commit()
        # rowcount is not always available on all drivers; run a count
        r3 = conn.execute(text("SELECT COUNT(*) FROM generated_papers WHERE teacher_id = :aid"), {"aid": admin_id})
        count = r3.scalar()
        print(f"  Assigned existing papers to admin (id={admin_id}). Papers now owned by admin: {count}")
    print("Migration assign_existing_papers_to_admin done.")


if __name__ == "__main__":
    run()
