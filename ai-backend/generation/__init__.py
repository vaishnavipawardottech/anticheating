"""
Question Paper Generation Pipeline
ai-backend/generation/

Steps:
1. Pattern Interpreter  — parse pattern text/PDF → JSON blueprint
2. Blueprint Builder    — map nature → Bloom, build QuestionSpec objects
3. Retrieval Engine     — hybrid retrieval per spec (unit-filtered, MMR, usage-balanced)
4. Question Generator   — LLM generation with answer key + marking scheme
5. CO Mapper            — unit_id → CO assignment
6. Paper Assembler      — build final paper with Q/OR-Q variants
7. Validator            — Bloom alignment, duplicate detection, grammar
8. Usage Tracker        — increment usage_count on consumed chunks
"""
