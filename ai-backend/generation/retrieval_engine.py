"""
Step 3 — Retrieval Engine

Hybrid retrieval (BM25 + vector) per QuestionSpec:
- Filters by subject_id, unit_id IN spec.units, blooms_level, difficulty
- Applies usage_count penalty
- MMR (Maximal Marginal Relevance) for diversity
- Returns top 3–5 chunks per question spec
"""

import math
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

from database.models import DocumentChunk, Document
from embeddings import get_embedding_generator
from embeddings.qdrant_manager import get_qdrant_manager
from generation.schemas import QuestionSpec


# ─── Constants ────────────────────────────────────────────────────────────────

RRF_K = 60
USAGE_PENALTY_BASE = 0.85       # per usage: score *= 0.85^usage_count
MMR_LAMBDA = 0.7                # diversity weight
MAX_CANDIDATES = 40
FINAL_CHUNK_COUNT = 5


# ─── Bloom level normalisation ────────────────────────────────────────────────

BLOOM_TO_INT = {
    "remember": 1, "understand": 2, "apply": 3,
    "analyze": 4, "evaluate": 5, "create": 6,
}


def _bloom_int_range(bloom_targets: List[str]) -> Tuple[Optional[int], Optional[int]]:
    """Convert bloom target strings to int range (min, max)."""
    ints = [BLOOM_TO_INT.get(b.lower(), 2) for b in bloom_targets]
    if not ints:
        return None, None
    return min(ints), max(ints)


# ─── MMR ─────────────────────────────────────────────────────────────────────

def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def mmr_select(
    candidates: List[dict],              # each: {chunk, score, embedding}
    query_vector: List[float],
    k: int = FINAL_CHUNK_COUNT,
    lambda_: float = MMR_LAMBDA,
) -> List[dict]:
    """
    Maximal Marginal Relevance selection.
    candidates: list of dicts with keys: chunk, score, embedding (list[float])
    Returns top-k selected candidates.
    """
    if len(candidates) <= k:
        return candidates

    selected = []
    remaining = candidates[:]

    while len(selected) < k and remaining:
        best = None
        best_score = float("-inf")
        for cand in remaining:
            rel = cand["score"]  # relevance score (normalised 0-1)
            # Diversity: max similarity to already-selected
            if selected:
                max_sim = max(_cosine(cand["embedding"], s["embedding"]) for s in selected)
            else:
                max_sim = 0.0
            mmr_score = lambda_ * rel - (1 - lambda_) * max_sim
            if mmr_score > best_score:
                best_score = mmr_score
                best = cand
        if best is None:
            break
        selected.append(best)
        remaining.remove(best)

    return selected


# ─── Usage penalty ────────────────────────────────────────────────────────────

def _apply_usage_penalty(score: float, usage_count: int) -> float:
    """Penalise chunks that have been used many times."""
    return score * (USAGE_PENALTY_BASE ** max(0, usage_count))


# ─── Main retrieval ───────────────────────────────────────────────────────────

def retrieve_chunks_for_spec(
    db: Session,
    spec: QuestionSpec,
    subject_id: int,
    top_k: int = FINAL_CHUNK_COUNT,
    exclude_chunk_ids: Optional[List[int]] = None,
) -> List[DocumentChunk]:
    """
    Step 3: Hybrid retrieval for one QuestionSpec.

    Returns up to top_k diverse, bloom-aligned, usage-balanced chunks.
    exclude_chunk_ids: chunk IDs already used in this generation run (to prevent repetition).
    """
    bloom_min, bloom_max = _bloom_int_range(spec.bloom_targets)
    difficulty = spec.difficulty if spec.difficulty != "auto" else None
    excluded: set = set(exclude_chunk_ids or [])

    # ── 1. BM25 (Postgres FTS) ─────────────────────────────────────────────
    fts_scores: dict = {}
    # Use nature as primary query term — much more specific than bloom names alone
    nature_query = (spec.nature or "") + " " + " ".join(spec.bloom_targets)
    q_escaped = nature_query.strip().replace("'", "''")
    if not q_escaped:
        q_escaped = "computer interaction design"

    try:
        clauses = ["d.subject_id = :sid"]
        params: dict = {"sid": subject_id, "q": q_escaped}

        # Unit filter
        if spec.units:
            clauses.append("c.unit_id = ANY(:units)")
            params["units"] = spec.units

        # Exclude already-used chunks
        if excluded:
            clauses.append("c.id != ALL(:excluded)")
            params["excluded"] = list(excluded)

        # Bloom filter
        if bloom_min is not None:
            clauses.append("(c.blooms_level_int IS NULL OR c.blooms_level_int >= :bmin)")
            params["bmin"] = bloom_min
        if bloom_max is not None:
            clauses.append("(c.blooms_level_int IS NULL OR c.blooms_level_int <= :bmax)")
            params["bmax"] = bloom_max

        # Difficulty filter
        if difficulty:
            clauses.append("(c.difficulty IS NULL OR c.difficulty = :diff)")
            params["diff"] = difficulty

        where = " AND ".join(clauses)
        # Try FTS first; if no query terms just fetch by unit/subject
        if q_escaped:
            sql = text(f"""
                SELECT c.id, ts_rank_cd(c.search_vector, plainto_tsquery('english', :q)) as rank
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE {where}
                  AND c.search_vector @@ plainto_tsquery('english', :q)
                ORDER BY rank DESC
                LIMIT {MAX_CANDIDATES}
            """)
        else:
            sql = text(f"""
                SELECT c.id, 1.0 as rank
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE {where}
                ORDER BY c.id
                LIMIT {MAX_CANDIDATES}
            """)
        rows = db.execute(sql, params).fetchall()
        for rank_1based, (cid, _) in enumerate(rows, start=1):
            fts_scores[cid] = 1.0 / (RRF_K + rank_1based)
    except Exception as e:
        print(f"[Retrieval] FTS error: {e}")

    # ── 2. Vector search (Qdrant) ──────────────────────────────────────────
    vector_scores: dict = {}
    try:
        gen = get_embedding_generator()
        query_text = f"{spec.nature or ''} {' '.join(spec.bloom_targets)} marks:{spec.marks}"
        query_vector = gen.generate_embedding(query_text)

        qdrant = get_qdrant_manager()
        raw_results = qdrant.search(
            query_vector=query_vector,
            limit=MAX_CANDIDATES,
            subject_id=subject_id,
            score_threshold=0.0,
        )

        for rank_1based, r in enumerate(raw_results, start=1):
            if r.get("point_type") == "chunk" and r.get("chunk_id") is not None:
                cid = r["chunk_id"]
                meta = r.get("metadata") or {}

                # Apply Bloom filter
                chunk_bloom_int = meta.get("blooms_level_int")
                if bloom_min is not None and chunk_bloom_int is not None:
                    if chunk_bloom_int < bloom_min:
                        continue
                if bloom_max is not None and chunk_bloom_int is not None:
                    if chunk_bloom_int > bloom_max:
                        continue

                # Apply unit filter
                chunk_unit_id = meta.get("unit_id")
                if spec.units and chunk_unit_id is not None:
                    if chunk_unit_id not in spec.units:
                        continue

                # Exclude already-used chunks
                if cid in excluded:
                    continue

                vector_scores[cid] = 1.0 / (RRF_K + rank_1based)
    except Exception as e:
        print(f"[Retrieval] Vector search error: {e}")

    # ── 3. Merge RRF ──────────────────────────────────────────────────────
    all_ids = set(fts_scores.keys()) | set(vector_scores.keys())
    merged = {
        cid: fts_scores.get(cid, 0.0) + vector_scores.get(cid, 0.0)
        for cid in all_ids
    }

    # ── 4. Fetch chunks from DB ───────────────────────────────────────────
    if not merged:
        # Fallback: unit-filtered, no bloom/difficulty constraint, still exclude used chunks
        fallback_params: dict = {"sid": subject_id}
        fallback_clauses = ["d.subject_id = :sid"]
        if spec.units:
            fallback_clauses.append("c.unit_id = ANY(:units)")
            fallback_params["units"] = spec.units
        if excluded:
            fallback_clauses.append("c.id != ALL(:excluded)")
            fallback_params["excluded"] = list(excluded)
        fallback_where = " AND ".join(fallback_clauses)
        fallback_sql = f"SELECT c.id FROM document_chunks c JOIN documents d ON d.id = c.document_id WHERE {fallback_where} ORDER BY RANDOM() LIMIT {MAX_CANDIDATES}"
        try:
            rows = db.execute(text(fallback_sql), fallback_params).fetchall()
            for i, (cid,) in enumerate(rows, start=1):
                merged[cid] = 1.0 / (RRF_K + i)
        except Exception:
            pass

    if not merged:
        return []

    sorted_ids = sorted(merged, key=lambda x: -merged[x])[:MAX_CANDIDATES]
    chunk_map = {
        c.id: c
        for c in db.query(DocumentChunk).filter(DocumentChunk.id.in_(sorted_ids)).all()
    }

    # ── 5. Apply usage penalty ────────────────────────────────────────────
    candidates = []
    for cid in sorted_ids:
        chunk = chunk_map.get(cid)
        if chunk is None or not chunk.text:
            continue
        base_score = merged[cid]
        usage_count = chunk.usage_count if chunk.usage_count is not None else 0
        penalised = _apply_usage_penalty(base_score, usage_count)
        emb = chunk.embedding_vector if chunk.embedding_vector is not None else []
        candidates.append({"chunk": chunk, "score": penalised, "embedding": emb})

    # ── 6. MMR selection ──────────────────────────────────────────────────
    try:
        gen = get_embedding_generator()
        query_vector_for_mmr = gen.generate_embedding(
            f"{spec.nature or ''} {' '.join(spec.bloom_targets)}"
        )
    except Exception:
        query_vector_for_mmr = []

    selected = mmr_select(candidates, query_vector_for_mmr, k=top_k)
    return [s["chunk"] for s in selected]
