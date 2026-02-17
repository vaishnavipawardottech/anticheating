# How to Test the Changes

## 1. Start infrastructure

```bash
cd ai-backend && docker compose up -d
```

Wait a few seconds for Postgres and Qdrant to be ready.

## 2. Run migrations (create new tables)

From the **project root**:

```bash
./run-migrations.sh
```

This runs `create_tables.py` (which now creates `document_chunks`, `exams`, `questions`, `question_sources`) and any other migrations.

## 3. Start the backend

```bash
cd ai-backend
source .venv/bin/activate   # or: .venv\Scripts\activate on Windows
python structure_api.py
```

Backend should be at **http://localhost:8001**. Ensure `ai-backend/.env` has `GOOGLE_API_KEY` for alignment and exam generation.

## 4. (Optional) Create Qdrant collection with new indexes

If you already had a Qdrant collection, recreate it so the new payload indexes (`concept_id`, `unit_id`, `section_path`) exist:

```bash
cd ai-backend && source .venv/bin/activate
python -c "
from embeddings.qdrant_manager import get_qdrant_manager
qm = get_qdrant_manager()
qm.create_collection(recreate=True)
"
```

## 5. Quick API checks

In another terminal (with backend running):

```bash
# Health
curl -s http://localhost:8001/health

# Search health (embedding + Qdrant)
curl -s http://localhost:8001/search/health

# Document routes (no double /documents/)
curl -s http://localhost:8001/documents/1          # get doc 1 (404 if none)
curl -s http://localhost:8001/documents/1/elements # elements for doc 1
```

## 6. End-to-end flow

1. **Create subject + units + concepts**  
   Use the app: **Ingest** → normalize syllabus, create subject/units/concepts. Or via API:
   - `POST /subjects/` → create subject
   - `POST /units/` → create units
   - `POST /concepts/` → create concepts

2. **Upload a document**  
   In the app: **Ingest** → choose subject → upload PDF/PPTX/DOCX.  
   Or: `POST /documents/upload-and-store` with `file` + `subject_id` (form-data).  
   This runs: parse → cleanup → classify → **chunk** → embed elements + chunks → index to Qdrant.

3. **(Optional) Align document to concepts**  
   `POST /alignment/align-document` with `{"document_id": 1}` to persist concept tags to elements and update chunk payloads in Qdrant.

4. **Semantic search**  
   `POST /search/semantic` with body:
   ```json
   { "query": "virtual memory", "subject_id": 1, "limit": 5 }
   ```
   You should get elements or chunks back.

5. **Context build**  
   `POST /context/build` with body:
   ```json
   { "subject_id": 1, "top_k": 10, "max_tokens": 2000 }
   ```
   Returns `context_text` and `citations`.

6. **Generate exam**  
   In the app: **Create Exam** → select subject (and units) → set MCQ/short/long counts → **Generate exam**.  
   Or: `POST /exams/generate` with body:
   ```json
   {
     "subject_id": 1,
     "unit_ids": [1, 2],
     "counts": { "mcq": 5, "short": 2, "long": 1 },
     "include_answer_key": true
   }
   ```
   Returns `exam_id`, `questions_generated`, `seed`.

## 7. Start the frontend

```bash
cd frontend && npm run dev
```

Open **http://localhost:5173** → **Create Exam** (or **Exams** → Create). Use the blueprint form: subject, units, counts, then **Generate exam**.

## Where to see embeddings (elements + chunks)

| What | Where |
|------|--------|
| **Element embeddings** | **API:** `GET /documents/elements-with-embeddings` (optional `?document_id=1`). **UI:** Sidebar → **Vectors Explorer** (shows parsed_elements with vector_id, text preview, embed dim). |
| **Chunk embeddings** | **API:** `GET /documents/chunks-with-embeddings` (optional `?document_id=1`). Returns chunk id, document_id, chunk_index, text_preview, section_path, page range, vector_id, embed_dim. **DB:** Table `document_chunks` (columns `embedding_vector`, `vector_id`, `section_path`). |
| **Total indexed vectors** | **API:** `GET /search/health` → `indexed_vectors` is total points in Qdrant (elements + chunks). Goes up after each ingest. |
| **Qdrant (raw points)** | Qdrant UI at http://localhost:6333/dashboard (if running). Collection `academic_elements`: each point has payload `point_type` ("element" or "chunk"), `chunk_id` for chunks, `section_path`, etc. |
| **Search results** | `POST /search/semantic` returns hits from both elements and chunks; chunk hits are enriched with chunk text and metadata. |

## Troubleshooting

| Issue | Check |
|-------|--------|
| `document_chunks` / `exams` table missing | Run `./run-migrations.sh` (create_tables.py now includes new models). |
| Search returns nothing | Ingest at least one document; check `/search/health` (indexed_vectors > 0). |
| Exam generate "Insufficient context" | Ingest documents for that subject; optionally run alignment. |
| 404 on `/documents/documents/1` | Use `/documents/1` (routes were fixed to avoid double prefix). |
| **"Not Found" / 404 when clicking Generate exam** | **Restart the backend** so the `/exams` router is loaded. Then check `curl -s http://localhost:8001/exams/` returns `{"status":"ok",...}`. |
| Qdrant filter by concept_id not working | Recreate collection (step 4) and re-ingest, or run alignment so chunk payloads get `concept_id`. |
