#!/usr/bin/env bash
# Run DB migrations. Requires Docker (Postgres) to be running.
# Start Docker Desktop, then: cd ai-backend && docker compose up -d
# Then run this script from the project root.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/ai-backend"

echo "=== Running DB migrations ==="
source .venv/Scripts/activate

echo "1. Creating tables (create_tables.py)..."
python create_tables.py

echo "2. Running migration: add_embedding_vector..."
python migrations/add_embedding_vector.py

echo "3. Running migration: alter_section_path_to_text..."
python migrations/alter_section_path_to_text.py

echo "4. Running migration: add_section_path_and_embedding_meta..."
python migrations/add_section_path_and_embedding_meta.py

echo "5. Running migration: add_chunk_search_vector (FTS for hybrid search)..."
python migrations/add_chunk_search_vector.py

echo "=== Migrations complete ==="
