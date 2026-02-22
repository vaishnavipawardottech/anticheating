# Smart Assessment — How to Start (Presentation Guide)

Quick steps to run the project for a live demo.

---

## Before the presentation (do this once)

### 1. Start Docker Desktop
- Required for **PostgreSQL**, **Qdrant**, and **Ollama**.
- Wait until Docker is fully running.

### 2. Start database and services
```bash
cd ai-backend && docker compose up -d
```
- Postgres: port **5432**
- Qdrant: port **6333**
- Ollama: port **11434**

### 3. Run migrations (if not done already)
From the **project root**:
```bash
./run-migrations.sh
```

### 4. Check API keys in `ai-backend/.env`
- `GOOGLE_API_KEY` — for syllabus structure AI (Gemini)
- `OPENAI_API_KEY` — for embeddings, alignment, question generation

---

## Starting the app (for the demo)

Use **two terminals**.

### Terminal 1 — AI backend (port 8001)
```bash
cd ai-backend
source .venv/bin/activate    # Windows: .venv\Scripts\activate
python structure_api.py
```
Wait until you see: `Uvicorn running on http://0.0.0.0:8001`

### Terminal 2 — Frontend (port 5173)
```bash
cd frontend
npm run dev
```
Wait until you see: `Local: http://localhost:5173/`

### Open in browser
- **App:** http://localhost:5173  
- **API docs (Swagger):** http://localhost:8001/docs  
- **Health check:** http://localhost:8001/health  

---

## Demo flow (what to show)

1. **Login** — Use the app login screen (or skip if no auth).
2. **Subjects** — Create or open a subject (e.g. "Operating Systems").
3. **Structure** — Add Units and Concepts (or use **Structure AI** to paste syllabus text and get a draft).
4. **Documents** — Upload a PDF/PPTX/DOCX; show parsing → chunks → indexing.
5. **Search** — Semantic or hybrid search on the ingested content.
6. **Generate** — Generate MCQ or subjective paper from pattern/text; show preview and export.

---

## One-line checklist

| Step | Command / Action |
|------|------------------|
| Docker up | `cd ai-backend && docker compose up -d` |
| Migrations | `./run-migrations.sh` |
| Backend | `cd ai-backend && source .venv/bin/activate && python structure_api.py` |
| Frontend | `cd frontend && npm run dev` |
| Open app | http://localhost:5173 |

---

## If something fails

- **"Can't connect to database"** → Docker not running or migrations not run. Run `docker compose up -d` and `./run-migrations.sh`.
- **"OPENAI_API_KEY not set"** → Add it to `ai-backend/.env`.
- **Port already in use** → Stop the other process using 8001 or 5173, or change the port in `structure_api.py` / `vite.config.js`.
- **Frontend can't reach backend** → Confirm backend is on http://localhost:8001 and CORS is allowed; frontend uses `http://localhost:8001` as API base.

---

## Quick test (no UI)

```bash
curl http://localhost:8001/health
curl http://localhost:8001/docs   # open in browser for Swagger
```

Good luck with your presentation.
