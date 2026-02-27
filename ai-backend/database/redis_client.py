"""
Redis client for MCQ exam auto-save.
Stores student answers in Redis hash during exam taking.
"""

import os
import json
from typing import Optional

import redis

# ─── Config ────────────────────────────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    """Get or create Redis connection."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


# ─── Key helpers ───────────────────────────────────────────────────────────────

def _exam_key(exam_id: int, student_id: int) -> str:
    return f"mcq_exam:{exam_id}:student:{student_id}"


# ─── Auto-save operations ─────────────────────────────────────────────────────

def save_answer(exam_id: int, student_id: int, question_id: int, selected_option: str, ttl_minutes: int = 120):
    """Save a single answer to Redis. TTL ensures cleanup even if submit never happens."""
    r = get_redis()
    key = _exam_key(exam_id, student_id)
    r.hset(key, str(question_id), selected_option)
    # Reset TTL on every save
    r.expire(key, ttl_minutes * 60)


def get_all_answers(exam_id: int, student_id: int) -> dict:
    """Get all saved answers for a student's exam. Returns {question_id_str: selected_option}."""
    r = get_redis()
    key = _exam_key(exam_id, student_id)
    return r.hgetall(key)


def clear_answers(exam_id: int, student_id: int):
    """Delete all saved answers for a student's exam (after submit)."""
    r = get_redis()
    key = _exam_key(exam_id, student_id)
    r.delete(key)
