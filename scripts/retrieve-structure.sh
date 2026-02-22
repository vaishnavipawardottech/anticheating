#!/usr/bin/env bash
# Retrieve Subject → Unit → Concept structure from the API
# Usage: ./scripts/retrieve-structure.sh [BASE_URL]
# Example: ./scripts/retrieve-structure.sh
#          ./scripts/retrieve-structure.sh http://localhost:8001

BASE="${1:-http://localhost:8001}"

echo "=== Subjects (list) ==="
curl -s "${BASE}/subjects/" | python3 -m json.tool

echo ""
echo "=== Subjects with stats (doc/unit/concept counts) ==="
curl -s "${BASE}/subjects/with-stats/all" | python3 -m json.tool

echo ""
echo "=== Subject by ID (e.g. 1) ==="
curl -s "${BASE}/subjects/1" | python3 -m json.tool

echo ""
echo "=== Subject with units (e.g. subject_id=1) ==="
curl -s "${BASE}/subjects/1/with-units" | python3 -m json.tool

echo ""
echo "=== Subject complete: subject → units → concepts (e.g. subject_id=1) ==="
curl -s "${BASE}/subjects/1/complete" | python3 -m json.tool

echo ""
echo "=== Units by subject (e.g. subject_id=1) ==="
curl -s "${BASE}/units/subject/1" | python3 -m json.tool

echo ""
echo "=== Unit by ID (e.g. unit_id=1) ==="
curl -s "${BASE}/units/1" | python3 -m json.tool

echo ""
echo "=== Unit with concepts (e.g. unit_id=1) ==="
curl -s "${BASE}/units/1/with-concepts" | python3 -m json.tool

echo ""
echo "=== Concepts by unit (e.g. unit_id=1) ==="
curl -s "${BASE}/concepts/unit/1" | python3 -m json.tool

echo ""
echo "=== Concept by ID (e.g. concept_id=1) ==="
curl -s "${BASE}/concepts/1" | python3 -m json.tool

echo ""
echo "=== Diagram-critical concepts (optional: ?subject_id=1) ==="
curl -s "${BASE}/concepts/diagram-critical" | python3 -m json.tool
