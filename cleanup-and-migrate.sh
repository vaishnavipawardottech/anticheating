#!/usr/bin/env bash
# Reset the database and run all migrations from scratch.
# Requires Docker (Postgres) to be running: cd ai-backend && docker compose up -d
# Run from project root.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Cleanup: reset database ==="
cd ai-backend
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
else
  source .venv/Scripts/activate
fi
python reset_db.py
cd "$SCRIPT_DIR"

echo ""
echo "=== Running migrations ==="
./run-migrations.sh

echo ""
echo "=== Done. Database reset and migrations complete. ==="
