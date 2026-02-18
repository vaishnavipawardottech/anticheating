# Smart Assessment – Current Architecture (As Implemented)

```
┌──────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                              │
├──────────────────────────────────────────────────────────────────────┤
│  Teacher Portal:                                                     │
│  • Login / Profile / Change password                                 │
│  • Subjects list → Subject detail (Units, Concepts, Documents)        │
│  • Ingest: Upload PDF/PPTX/DOCX → parse + store + embed              │
│  • Remove document (per-document delete)                             │
│  • Vectors Explorer: elements/chunks, embedding status, filters      │
│  • Create Exam: blueprint (MCQ/short/long counts) → generate         │
│  • All Exams: list generated exams                                   │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ REST API (port 8001)
┌────────────────────────────▼─────────────────────────────────────────┐
│                    BACKEND (FastAPI)                                  │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────── LAYER 1: INGESTION ──────────────────┐        │
│  │                                                           │        │
│  │  [Document Upload & Store]  POST /documents/upload-and-store
│  │         ↓                                                 │        │
│  │  [Unstructured Parser]  parsing/document_parser.py         │        │
│  │    • PDF / PPTX / DOCX (explicit per type)                │        │
│  │    • Element extraction (Title, NarrativeText, ListItem…)  │        │
│  │    • Page number, metadata                                 │        │
│  │         ↓                                                 │        │
│  │  [Cleanup Engine]  parsing/cleanup.py                      │        │
│  │    • Headers/footers, page numbers, TOC leaders           │        │
│  │    • Pure numeric, symbol/bullet-only, CID artifacts      │        │
│  │         ↓                                                 │        │
│  │  [Element Classifier]  parsing/classifier.py               │        │
│  │    • TEXT, DIAGRAM, TABLE, CODE, FORMULA, OTHER           │        │
│  │    • Diagram-critical detection                           │        │
│  │         ↓                                                 │        │
│  │  [Section Paths]  chunker.compute_section_paths_for_elements
│  │    • Heading stack → section_path per element             │        │
│  │         ↓                                                 │        │
│  │  [Smart Chunker]  parsing/chunker.py                      │        │
│  │    • prepare_for_chunking: drop junk, merge fragments,     │        │
│  │      dedup; then chunk by meaning                         │        │
│  │    • Section-aware: Unit/1.1 push path; Note/Figure attach │        │
│  │      to next body; ~150–350 tokens + overlap              │        │
│  │    • Semantic split: when over size limit, use embeddings │        │
│  │      to break at topic boundary (lowest similarity       │        │
│  │      between consecutive parts) instead of mid-thought   │        │
│  │    • Enrich: "Path: Unit I > …" prefix for embedding      │        │
│  │    • Table → table_schema chunk + table_row chunks        │        │
│  │         ↓                                                 │        │
│  │  [Embedding Generator]  embeddings/generator.py           │        │
│  │    • all-MiniLM-L6-v2 (384-dim), batch                    │        │
│  │         ↓                                                 │        │
│  │  [Storage]                                                │        │
│  │    • PostgreSQL: documents, parsed_elements, document_chunks
│  │    • Qdrant: academic_chunks (main), academic_elements     │        │
│  │    • Embedding metadata: model, dim, embedded_at          │        │
│  │                                                           │        │
│  │  [Parse-only API]  POST /documents/parse  (no DB/store)    │        │
│  │  [Cleanup API]    POST /cleanup/apply                     │        │
│  │                                                           │        │
│  └───────────────────────────────────────────────────────────┘        │
│                                                                       │
│  ┌─────────────────── LAYER 2: STRUCTURE ──────────────────┐        │
│  │                                                           │        │
│  │  [Academic Hierarchy]  /subjects, /units, /concepts       │        │
│  │    • CRUD Subjects, Units, Concepts                       │        │
│  │    • subjects/with-stats/all, subjects/:id/with-documents │        │
│  │         ↓                                                 │        │
│  │  [Structure AI]  /structure  (advisory, no DB write)      │        │
│  │    • Normalize raw syllabus → UnitDraft + concepts         │        │
│  │    • Gemini (OpenAI-compatible API)                       │        │
│  │         ↓                                                 │        │
│  │  [Alignment Engine]  /alignment                            │        │
│  │    • Align ParsedElements or DocumentChunks → Concepts    │        │
│  │    • Gemini + optional embedding similarity               │        │
│  │    • Writes: concept_id, alignment_confidence on elements │        │
│  │      or chunks; AlignedElement records                     │        │
│  │                                                           │        │
│  └───────────────────────────────────────────────────────────┘        │
│                                                                       │
│  ┌──────────────── SEARCH & CONTEXT ──────────────────────┐        │
│  │  [Semantic Search]  POST /search/semantic                 │        │
│  │  [Hybrid Search]   POST /search/hybrid                   │        │
│  │  [Context Builder] POST /context/build                    │        │
│  └───────────────────────────────────────────────────────────┘        │
│                                                                       │
│  ┌──────────── LAYER 3: QUESTION BANK (concept-centric) ───────────┐  │
│  │  Input: concept_id (or unit_id/subject_id); target counts       │  │
│  │  • Concept context pack: chunks with alignment_confidence ≥ 0.65  │  │
│  │    → MMR diversify → 3–8 chunks (token-safe)                     │  │
│  │  • Generate: LLM (Gemini) → 2×MCQ, 1×Short, 1×Long per concept   │  │
│  │    Output: strict Question JSON (source_chunk_ids, Bloom, etc.)  │  │
│  │  • Bloom classifier: rule-based (verbs) + LLM verifier          │  │
│  │  • Validator gates: groundedness, MCQ sanity, ambiguity, dedupe  │  │
│  │    (Qdrant question_embeddings: same-concept >0.90, global >0.95)│  │
│  │  • Store: question_bank, bank_question_sources, quality_scores,   │  │
│  │    question_generation_runs                                     │  │
│  │  POST /questions/generate   GET /questions   approve/reject/PATCH│  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌──────────────── LAYER 4: EXAM GENERATION ───────────────┐        │
│  │                                                           │        │
│  │  [Exam Generator]  POST /exams/generate                   │        │
│  │    Input: subject_id, unit_ids/concept_ids, counts        │        │
│  │           (mcq, short, long), difficulty/bloom dist, seed │        │
│  │         ↓                                                 │        │
│  │    • Expand blueprint → per-concept demand                │        │
│  │    • build_context_impl (semantic or filter, top_k chunks)│        │
│  │    • Single LLM call (Gemini): context → JSON questions   │        │
│  │    • Types: mcq (4 options), short, long                  │        │
│  │    • answer_key: correct_option, key_points, rubric…       │        │
│  │    • difficulty, bloom_level per question                 │        │
│  │         ↓                                                 │        │
│  │  [Storage]  Exam + Question rows; QuestionSource → chunk  │        │
│  │  [List]     GET /exams (by subject)                       │        │
│  │                                                           │        │
│  │  No: template manager, constraint engine, paper formatter, │        │
│  │      PDF/Word export (yet)                                │        │
│  │                                                           │        │
│  └───────────────────────────────────────────────────────────┘        │
│                                                                       │
│  ┌────────────────── DOCUMENTS & VECTORS API ─────────────────┐      │
│  │  GET  /documents/embedding-status   (badge, by-doc counts) │      │
│  │  GET  /documents/elements-with-embeddings  (filters)       │      │
│  │  GET  /documents/chunks-with-embeddings                    │      │
│  │  GET  /documents/:id, /documents/:id/elements              │      │
│  │  DELETE /documents/:id  (DB + Qdrant + file)               │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                       │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────────┐
│                    DATA LAYER                                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────── PostgreSQL ─────────────────────────────────┐      │
│  │  • subjects (id, name, description)                        │      │
│  │  • units (id, subject_id, name, order)                     │      │
│  │  • concepts (id, unit_id, name, diagram_critical, order)  │      │
│  │  • documents (id, filename, file_type, file_path,          │      │
│  │               subject_id, status, upload_timestamp)        │      │
│  │  • parsed_elements (id, document_id, order_index,          │      │
│  │      element_type, category, text, page_number,            │      │
│  │      section_path, vector_id, embedding_model, dim, …)     │      │
│  │  • document_chunks (id, document_id, chunk_index, text,    │      │
│  │      section_path, page_start/end, source_element_orders,  │      │
│  │      token_count, chunk_type, table_id, row_id,            │      │
│  │      vector_id, embedding_*, search_vector tsvector)       │      │
│  │  • aligned_elements (element data + concept_id, status)    │      │
│  │  • exams (id, subject_id, blueprint, seed)                 │      │
│  │  • questions (id, exam_id, type, text, answer_key,         │      │
│  │      difficulty, bloom_level)                             │      │
│  │  • question_sources (question_id, chunk_id, page_start/end)│      │
│  │  • question_bank (Layer 3: concept/unit/CO/Bloom, status)  │      │
│  │  • bank_question_sources, question_generation_runs,        │      │
│  │    question_quality_scores                                  │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                       │
│  ┌──────────────── Qdrant ───────────────────────────────────┐      │
│  │  academic_chunks  (main retrieval)                         │      │
│  │    • 384-dim vectors, payload: document_id, subject_id,   │      │
│  │      unit_id, concept_id, section_path, chunk_type,        │      │
│  │      table_id, row_id, page_start/end                      │      │
│  │  academic_elements  (optional element-level search)       │      │
│  │  question_embeddings  (Layer 3 dedupe & search)          │      │
│  │  Use: semantic + hybrid (FTS + vector) search             │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                       │
│  Redis: not used                                                      │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                              │
├───────────────────────────────────────────────────────────────────────┤
│  • Google Gemini (OpenAI-compatible): structure AI, alignment,       │
│    exam question generation                                           │
│  • SentenceTransformers (local): all-MiniLM-L6-v2 embeddings         │
│  • Document storage: local filesystem (uploads/)                      │
└───────────────────────────────────────────────────────────────────────┘
```

## Differences: flow.md (target) vs ARCHITECTURE.md (current)

| Area | flow.md (target) | Current (ARCHITECTURE.md) |
|------|------------------|---------------------------|
| **Frontend** | Upload docs, define structure, **map Course Outcomes**, **review question bank**, generate papers, **export PDFs** | Login/profile, subjects list/detail, ingest, **remove document**, **Vectors Explorer**; create exam, all exams. **No CO mapping UI, no question bank review, no PDF export.** |
| **Ingestion – Chunker** | “Semantic Chunker”: 500–1000 token chunks, 100-token overlap | **Smart chunker**: prepare (junk/fragment/dedup) → section-aware ~150–350 tokens, path prefix, **table_schema + table_row** chunks; **section_path** per element; **parse-only + cleanup APIs** |
| **Ingestion – Storage** | “chunks + metadata” in Postgres; Qdrant for embeddings | **parsed_elements** + **document_chunks** (with search_vector, table_id, row_id); **academic_chunks** + **academic_elements** in Qdrant; embedding metadata (model, dim, embedded_at) |
| **Structure** | **Course Outcome Manager** (CO1, CO2…; map COs to units/concepts; Bloom per CO) | **No CO**. Academic hierarchy + Structure AI (syllabus → draft) + **Alignment** (elements/chunks → concepts, Gemini). |
| **Question generation** | **Layer 3**: Question **Bank** Generator (per-chunk LLM → 3–5 Q per chunk, store in bank) → **Bloom Classifier** → **Quality Validator** (grammar, duplicate, ambiguity) | **No question bank**. **Layer 4** exam: one **Exam** generator (blueprint → context → **single** LLM call → Exam + Questions); Bloom/difficulty in prompt. **No** Bloom classifier module, **no** quality validator. |
| **Paper generation** | **Layer 4**: **Template Manager** (ENDSEM/MIDSEM/Internal) → **Constraint engine** (unit/Bloom/CO/difficulty sampling, slot assignment) → **Paper Formatter** → **Export** (PDF, Word, Markdown) | **None**. Exams stored as Exam + Question rows; **no** templates, **no** constraint engine, **no** formatter, **no** PDF/Word export. |
| **Workflow** | **Layer 5**: **Background jobs** (Celery), **Review system** (approval, edit, versioning), **Analytics dashboard** | **None**. No background jobs, no review workflow, no analytics. |
| **Data – Postgres** | course_outcomes, co_mappings, **semantic_chunks**, **chunk_concept_alignment**, **question_bank** (approved, reviewed_by), **exam_templates**, **generated_papers** (status, template_id) | **No** CO tables. **parsed_elements**, **document_chunks** (incl. search_vector, chunk_type, table_id, row_id), **aligned_elements**; **exams**, **questions**, **question_sources**. **No** question_bank, exam_templates, or generated_papers. |
| **Data – Qdrant** | academic_chunks, text_preview (200 chars) | academic_chunks + academic_elements; payload includes section_path, chunk_type, table_id, row_id. **Hybrid search** (Postgres FTS + Qdrant). |
| **Data – Redis** | Cache, queue, session | **Not used** |
| **External** | OpenAI/Ollama, **MinIO/S3**, Email | **Gemini** (structure, alignment, exams), **local** SentenceTransformers, **local** filesystem (uploads/) |

**Summary:** flow.md describes the full target system (CO, question bank, templates, constraint-based paper generation, export, review, analytics, Redis). The current codebase implements ingestion (with a richer chunker and FTS), structure + alignment, semantic/hybrid search, context build, and **one-shot exam generation** (blueprint → LLM → Exam + Questions), but no CO, no question bank, no paper templates/constraint engine/export, and no workflow/analytics layer.
