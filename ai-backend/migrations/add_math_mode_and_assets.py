"""
Migration: Phase 1 — math_mode config + assets table.

- subjects: add math_mode, formula_mode, vision_budget (for DM-style ingestion).
- assets: new table for extracted images/tables/page snapshots; vision enrichment stores kind, caption, structured_json.
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


def _table_exists(conn, table: str) -> bool:
    r = conn.execute(text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
    ), {"t": table})
    return r.fetchone() is not None


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
        # ── subjects: math_mode, formula_mode, vision_budget ─────────────────────
        for col, dtype in [
            ("math_mode", "BOOLEAN NOT NULL DEFAULT false"),
            ("formula_mode", "BOOLEAN NOT NULL DEFAULT false"),
            ("vision_budget", "INTEGER"),
        ]:
            if not _column_exists(conn, "subjects", col):
                conn.execute(text(f"ALTER TABLE subjects ADD COLUMN {col} {dtype}"))
                conn.commit()
                print(f"Added subjects.{col}")
            else:
                print(f"subjects.{col} already exists")

        # ── assets table ──────────────────────────────────────────────────────────
        if not _table_exists(conn, "assets"):
            conn.execute(text("""
                CREATE TABLE assets (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    page_no INTEGER NOT NULL,
                    bbox JSONB,
                    sha256 VARCHAR(64),
                    asset_url VARCHAR(500) NOT NULL,
                    asset_type VARCHAR(20) NOT NULL,
                    source_element_order INTEGER,
                    kind VARCHAR(30),
                    caption TEXT,
                    structured_json JSONB,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
            """))
            conn.execute(text("CREATE INDEX ix_assets_document_id ON assets(document_id)"))
            conn.execute(text("CREATE INDEX ix_assets_page_no ON assets(page_no)"))
            conn.execute(text("CREATE INDEX ix_assets_sha256 ON assets(sha256)"))
            conn.execute(text("CREATE INDEX ix_assets_asset_type ON assets(asset_type)"))
            conn.execute(text("CREATE INDEX ix_assets_kind ON assets(kind)"))
            conn.commit()
            print("Created table assets and indexes")
        else:
            print("Table assets already exists")

    print("Migration add_math_mode_and_assets completed.")


if __name__ == "__main__":
    run()
