# Smart Assessment — Architecture Deep Dive

**International Hackathon | $3K Bounty**

This document describes the end-to-end architecture: data flow, pipelines, LLM usage, and design decisions.

---

## 1. Yes — We Use Prompting for Classification and More

**All of the following use LLM prompts** (OpenAI GPT or Google Gemini, depending on the module):

| Area | What | Model | Prompt role |
|------|------|--------|--------------|
| **Structure AI** | Raw syllabus → Subject/Units/Concepts draft | Gemini 2.5 Flash | Normalization prompt: extract hierarchy, preserve teacher wording, output strict JSON. |
| **Academic classification** | Chunk → section_type, Bloom’s, difficulty, source_type | GPT-3.5-turbo | System + user prompt: classify each chunk; JSON array per batch (10 chunks/call). |
| **Concept alignment** | Chunk → concept_id + confidence | GPT-4o-mini (structured) | Alignment prompt + JSON schema: map chunks to concepts; confidence &lt; 0.7 → unassigned. |
| **Image captioning** | Image → text description | GPT-4o (vision) | “Describe this academic image in detail” for diagrams/figures. |
| **Table formatting** | Raw table → Markdown | GPT (chat) | “Convert this table to Markdown” for clean table chunks. |
| **Exam generation (blueprint)** | Context + counts → JSON array of questions | Gemini Flash | “Generate exactly N MCQ/short/long from context”; JSON array. |
| **Question bank generation** | Context + concept → questions | Gemini Flash | Generator prompt + groundedness validator (Gemini). |
| **Pattern interpretation** | Exam pattern text/PDF → ParsedPattern | GPT | “Convert exam pattern to JSON” (units, marks, question_type, nature, expected_bloom). |
| **NL interpreter** | Teacher free text → MCQSpec / SubjectiveSpec | GPT | “Convert teacher request to JSON” with real unit_id list from DB. |
| **Question generation (paper)** | Context + QuestionSpec → single question | GPT | MCQ_PROMPT / DESCRIPTIVE_PROMPT with context, marks, Bloom, difficulty. |
| **Validation** | Generated question → bloom_ok, depth_ok, grammar, corrected text | GPT | “Review question; return bloom_ok, depth_ok, grammar_ok, corrected_question.” |

**Rule-based (no prompts):** Element classifier (TEXT/DIAGRAM/TABLE/CODE/FORMULA), chunking logic, FTS ranking, RRF/MMR, cosine similarity, usage penalty.

---

## 2. System Context and Goals

- **Users:** Teachers / faculty.
- **Goal:** Turn course materials (syllabus + PDF/PPTX/DOCX) into a structured, searchable knowledge base and generate exams (MCQ + subjective) with control over units, marks, difficulty, and Bloom’s level.
- **Constraints:** Use existing LLM APIs (OpenAI, Gemini), avoid reinventing retrieval (use Postgres + vector DB), keep structure as source of truth.

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React + Vite)                          │
│  Subjects • Structure AI • Ingest Document • Search • Generate Exam/Paper     │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AI BACKEND (FastAPI) — Port 8001                           │
│  /subjects, /units, /concepts, /structure, /documents, /search,               │
│  /context, /exams, /questions, /generation                                    │
└─────────────────────────────────────────────────────────────────────────────┘
         │                    │                    │                    │
         ▼                    ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  PostgreSQL  │    │   Qdrant     │    │  OpenAI API  │    │  Gemini API   │
│  (Structure, │    │  (Vectors)   │    │  Embeddings, │    │  Structure AI,│
│   chunks,    │    │  Chunk +     │    │  Classification│   │  Exam/Quest.  │
│   FTS)       │    │  Element idx │    │  Alignment,   │    │  Generation  │
└──────────────┘    └──────────────┘    │  Generation   │    └──────────────┘
                                        └──────────────┘
```

- **Frontend:** React SPA; talks only to the AI backend.
- **AI backend:** Single FastAPI app; owns structure, documents, search, context, exams, and generation.
- **PostgreSQL:** Source of truth (subjects, units, concepts, documents, parsed_elements, document_chunks, parent_contexts, exams, questions, question_bank, generated_papers). Also FTS (tsvector + GIN).
- **Qdrant:** Vector index only (chunk/element embeddings); no full text.
- **OpenAI:** Embeddings (text-embedding-3-small), academic classification, alignment (GPT-4o-mini structured), image captioning, table formatting, pattern/NL interpretation, question generation, validation.
- **Gemini:** Syllabus normalization (structure AI), blueprint exam generation, question-bank generation, groundedness checks.

---

## 4. Data Model (Simplified)

- **Subject** → **Unit** → **Concept** (syllabus hierarchy).
- **Document** (file metadata, status) → **ParsedElement** (per-element from parser; section_path, embedding_vector optional) and **DocumentChunk** (500-token-ish chunks; parent_id → ParentContext; search_vector, Bloom’s, difficulty, usage_count).
- **ParentContext:** Large sections (2000–4000 tokens); children chunks point here for RAG context.
- **Exam** + **Question** (blueprint-style); **GeneratedPaper** (pattern/NL pipeline); **QuestionSource** / **BankQuestion** for traceability and question bank.
- **AlignedElement:** Optional alignment of content to concepts (concept_id, confidence).

---

## 5. Ingestion Pipeline (Document → Searchable Chunks)

**Endpoint:** `POST /documents/upload-and-store` (and related document routes).

| Step | Name | What | Prompt / algo |
|------|------|------|----------------|
| 1 | Parse | PDF/PPTX/DOCX → elements (Unstructured) | — |
| 2 | Normalize | Unicode, CID, spacing, bullets | — |
| 3 | Caption images | Image elements → text | GPT-4o vision prompt |
| 4 | Format tables | Table elements → Markdown | GPT table prompt |
| 5 | Cleanup | Drop junk, merge fragments | Rule-based |
| 6 | Classify | Element → TEXT/DIAGRAM/TABLE/CODE/FORMULA | Rule-based (element_type + regex) |
| 7 | Chunk | Section-aware chunks (600–1000 chars, overlap) | Rule-based (+ optional semantic split) |
| 8 | Academic classify | Chunk → section_type, Bloom’s, difficulty, source_type | **GPT-3.5 prompt** (batch of 10) |
| 9 | Embed | Chunk text → 1536-dim vector | OpenAI text-embedding-3-small (no prompt) |
| 10 | Index | Chunks → Postgres + Qdrant; FTS trigger | — |
| (Optional) | Align | Chunk → concept_id, confidence | **GPT-4o-mini structured prompt** |

So: **prompting is used for** image captioning, table formatting, **academic classification**, and **concept alignment**. Parsing, normalization, cleanup, element category, and chunking are non-LLM.

---

## 6. Retrieval and Context Building — Algorithms

### 6.1 Full-text search (Postgres, “BM25-style”)

**Where:** `migrations/add_chunk_search_vector.py`, `routers/search.py`, `generation/retrieval_engine.py`

- **Storage:** Each `document_chunks` row has a `search_vector` column of type `tsvector`, maintained by a DB trigger on insert/update of `text` and `section_path`.
- **Build rule:**
  - `search_vector = setweight(to_tsvector('english', text), 'A') || setweight(to_tsvector('english', section_path), 'B')`
  - Body `text` gets weight **A**, `section_path` (headings) gets weight **B** so body matches rank higher than path-only matches.
- **Query:** User query string is passed to `plainto_tsquery('english', q)` (normalized, stemmed, AND of words).
- **Match:** `search_vector @@ plainto_tsquery('english', q)` (contains query terms).
- **Ranking:** `ts_rank_cd(search_vector, plainto_tsquery('english', q))` — cover density ranking (proximity and frequency). Results ordered by this rank DESC, then we only use **rank position** for RRF (see below).
- **Index:** GIN on `search_vector` for fast FTS.

So: **keyword/phrase match + stemmed English + weighted body vs path + proximity-aware rank**. We do **not** use a true BM25 formula; we use Postgres FTS rank and then feed ranks into RRF.

---

### 6.2 Vector (semantic) search

**Where:** `embeddings/qdrant_manager.py`, `embeddings/generator.py`

- **Query:** Query string → OpenAI `text-embedding-3-small` → 1536-dim vector.
- **Search:** Qdrant is called with this vector; **distance = cosine** (config: `Distance.COSINE`). Qdrant returns points sorted by **similarity** (higher = more similar).
- **Cosine similarity:** For vectors **a**, **b**:  
  `score = dot(a,b) / (||a|| * ||b||)`  
  In [0, 1] when vectors are non-negative (typical for embeddings). Used for: Qdrant retrieval, MMR diversity, duplicate detection, semantic split in chunker.
- **Filters:** Subject (and optionally document, unit, concept, Bloom, difficulty, usage_count) applied via Qdrant payload filters so only eligible chunks are returned.
- **Score used in pipeline:** We again use **rank position** (1st, 2nd, …) for RRF, not the raw cosine value.

So: **embed query → nearest-neighbor search in Qdrant (cosine) → ranked list of chunk IDs**.

---

### 6.3 RRF (Reciprocal Rank Fusion)

**Where:** `routers/search.py` (hybrid), `generation/retrieval_engine.py`

- **Purpose:** Merge two (or more) ranked lists — e.g. FTS list and vector list — without normalizing their raw scores (which are on different scales).
- **Formula:** For each item, assign a contribution from each list it appears in:  
  **contribution = 1 / (k + rank)**  
  with **rank** = 1-based position in that list. We use **k = 60** everywhere.
- **Merge:** Per chunk_id, **RRF_score = sum over all lists of (1 / (k + rank))** (missing list ⇒ 0). Chunks are then sorted by **RRF_score** descending.
- **Properties:** Items that rank well in **both** lists get a higher sum; items in only one list still get a non-zero score. No need to tune FTS vs vector score scales.

So: **FTS ranks + vector ranks → per-item RRF sum → final ordering**.

---

### 6.4 Optional rerank: keyword overlap

**Where:** `routers/search.py` — `_rerank_by_keyword_overlap()`

- **When:** After RRF merge, if `rerank_top_n` is set (e.g. take top 30, rerank, then return top 8).
- **Algorithm:**
  - Extract query terms: `terms = set(re.findall(r"\w+", query.lower()))`.
  - For each chunk in the top-N list, **overlap_score = (number of query terms that appear in chunk text) / |terms|** (fraction of query terms found).
  - Reorder the top-N by **overlap_score** descending (then by original order for ties).
- **Purpose:** Boost chunks that actually contain the query words while still benefiting from semantic retrieval in the earlier stage.

So: **simple term-overlap rerank on the merged list**.

---

### 6.5 Context building (for RAG / generation)

**Where:** `routers/context.py` — `build_context_impl()`

- **Input:** subject_id, optional query, optional unit_id / concept_ids, top_k (e.g. 15), include_neighbors (default true), max_tokens (e.g. 4000), min_score (for vector).
- **Retrieval:**
  - **If query given:** Embed query → Qdrant search with subject/unit/concept filters and score_threshold = min_score → list of (chunk_id, score). Order preserved by Qdrant rank; we only use chunk IDs and optionally scores.
  - **If no query:** DB query for chunks in that subject/unit/concept, ordered by document_id and chunk_index; take first top_k. No scoring.
- **Dedupe:** Collect chunk IDs in order; skip duplicates (ids_seen).
- **Neighbors (include_neighbors=true):** For each retrieved chunk, add chunks from the **same document** with `|chunk_index - self.chunk_index| <= 1` (immediate prev/next). Adds continuity without a second retrieval.
- **Token budget:** Approximate tokens as `words * 1.3`. Walk chunks in order; append text until **total_tokens** would exceed max_tokens. If adding a chunk would exceed the cap, **truncate that chunk** to fit: `keep_words = (max_tokens - total_tokens) / 1.3`, take first keep_words words.
- **Output:** Concatenated context string (chunks separated by `\n\n---\n\n`) and a list of citations (chunk_id, page, filename).

So: **retrieve by vector (or by filter) → optionally add neighbors → fill up to max_tokens with optional truncation of last chunk**.

---

### 6.6 Retrieval engine (paper pipeline, per QuestionSpec)

**Where:** `generation/retrieval_engine.py` — `retrieve_chunks_for_spec()`

Used when generating a **single** question from a spec (nature, bloom_targets, units, difficulty, marks). Goal: return a small set of **diverse, relevant** chunks, avoiding overuse of the same chunks.

1. **FTS branch:** Build query from `nature + " ".join(bloom_targets)`; run Postgres FTS with unit/bloom/difficulty/exclude filters; take up to MAX_CANDIDATES (40); assign **RRF contribution** per rank: `1/(RRF_K + rank)`.
2. **Vector branch:** Embed same-style query (nature + bloom_targets + "marks:N"); Qdrant search with subject/unit filters; apply Bloom/difficulty/unit filters on payload; exclude already-used chunk IDs; assign same RRF contribution per rank.
3. **Merge RRF:** For each chunk_id, **merged_score = fts_contribution + vector_contribution** (missing = 0). Sort by merged_score DESC; keep top MAX_CANDIDATES chunk IDs.
4. **Fallback:** If no results (e.g. no FTS match), random sample from DB with same filters and assign synthetic RRF scores.
5. **Usage penalty:** For each candidate chunk, **penalised_score = base_score * (0.85 ^ usage_count)**. So chunks already used for generation are down-weighted (constant **USAGE_PENALTY_BASE = 0.85**).
6. **MMR (Maximal Marginal Relevance):** From the penalised candidates (with embeddings loaded), select **top k** (e.g. 5) using MMR:
   - **MMR_score(candidate) = λ * relevance − (1 − λ) * max_similarity_to_selected**
   - **relevance** = penalised_score (normalised to 0–1 if needed; in code we use the penalised score as “relevance”).
   - **max_similarity_to_selected** = max over already-selected chunks of **cosine(candidate.embedding, selected.embedding)**.
   - **λ = 0.7** (MMR_LAMBDA): favours relevance over diversity; higher (1−λ) would favour more diversity.
   - Greedy: repeatedly pick the candidate with highest MMR_score, add to selected, until we have k.

**Result:** Up to **top_k** (e.g. 5) chunks per QuestionSpec that are relevant (FTS + vector), not overused (usage penalty), and diverse (MMR).

---

### 6.7 Summary table

| Algorithm | Role | Parameters / formula |
|-----------|------|----------------------|
| Postgres FTS | Keyword match + rank | tsvector A/B weights, plainto_tsquery, ts_rank_cd |
| Vector search | Semantic similarity | Cosine in Qdrant, 1536-dim, score_threshold |
| RRF | Merge FTS + vector lists | 1/(k+rank), k=60, sum per item |
| Keyword rerank | Boost exact term match | Overlap = \|terms in chunk\| / \|terms\| |
| Neighbor expansion | Context continuity | chunk_index ± 1 in same document |
| Token cap | Fit context in budget | words×1.3, truncate last chunk if needed |
| Usage penalty | Prefer fresh chunks | score × 0.85^usage_count |
| MMR | Diversity in selection | λ·rel − (1−λ)·max_sim_to_selected, λ=0.7 |

---

## 7. Generation Pipelines

### 7.1 Blueprint exam (`/exams/generate`)

- Input: subject_id, unit/concept filters, counts (MCQ, short, long).
- Build context (no query; by unit/concept); then **one Gemini Flash prompt** to produce a JSON array of questions; validate; store Exam + Questions.

### 7.2 Question bank (concept-centric)

- Per concept/unit: retrieve chunks → context → **Gemini Flash** generator prompt → questions; **groundedness validator** (Gemini); store in question_bank with source_chunk_ids.

### 7.3 Pattern-based paper (`/generation`)

- **Pattern path:** Pattern text or PDF → **pattern interpreter (GPT)** → ParsedPattern (total_marks, questions[] with units, marks, question_type, nature, expected_bloom).
- **NL path:** Teacher text → **NL interpreter (GPT)** + DB units → MCQSpec or SubjectiveSpec (unit_distribution / sections).
- Then for each question spec: **retrieval_engine** (hybrid + MMR + usage penalty) → context → **question_generator (GPT)** (MCQ or descriptive prompt) → **validator (GPT)** (Bloom, depth, grammar, duplicate detection via embeddings) → assemble paper → store GeneratedPaper.

So **prompting** is used for: pattern interpretation, NL interpretation, **per-question generation**, and **validation**.

---

## 8. LLM and Prompting Strategy (Summary)

| Purpose | Model | Why |
|---------|--------|-----|
| Syllabus → structure draft | Gemini 2.5 Flash | Long context, cheap, good at following structure rules. |
| Chunk classification (academic) | GPT-3.5-turbo | Cost-effective batch classification, JSON output. |
| Chunk → concept alignment | GPT-4o-mini (structured) | Reliable JSON schema, good instruction following. |
| Image captioning / table format | GPT-4o / GPT | Vision and table understanding. |
| Exam (blueprint) / question bank | Gemini Flash | Good balance of cost and quality for bulk generation. |
| Pattern / NL interpretation | GPT | Precise spec parsing with unit list. |
| Single-question generation | GPT | MCQ and descriptive prompts with context. |
| Validation (quality + duplicates) | GPT | Per-question review and cosine-based dedupe. |

**Embeddings:** OpenAI text-embedding-3-small (1536-dim) for search, MMR, duplicate detection, and semantic split.

---

## 9. Technology Stack

| Layer | Choice |
|-------|--------|
| Frontend | React 19, Vite 7, Tailwind, Redux, React Router |
| Backend | FastAPI, Python 3.13 |
| Relational DB | PostgreSQL 15 (structure, chunks, FTS) |
| Vector DB | Qdrant (chunk/element embeddings) |
| LLMs | OpenAI (GPT-3.5/4o/4o-mini, embeddings), Google Gemini (Flash) |
| Parsing | Unstructured (PDF/PPTX/DOCX) |
| Deployment | Docker (Postgres, Qdrant, optional Ollama); backend/frontend run on host or containers |

---

## 10. Why This Fits a $3K International Hackathon

- **End-to-end product:** Syllabus → structure → ingest → search → exam/paper generation with clear user value.
- **Structured use of LLMs:** Prompts for classification, alignment, interpretation, generation, and validation; structured outputs and fallbacks where needed.
- **Hybrid retrieval:** Postgres FTS + Qdrant + RRF + MMR + usage penalty for diverse, relevant context.
- **Traceability:** Question sources and chunk usage tracked; alignment and confidence for review.
- **Scalable design:** Clear separation of structure, ingestion, retrieval, and generation; can swap models or add more pipelines without rewriting the core.

Use this document as the **single source of truth** for “what the system does” and “where prompting is used” in your presentation and submission.
