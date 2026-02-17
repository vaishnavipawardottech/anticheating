# smart-assessment

## Running the project

### 1. Start Docker (required for Postgres, Qdrant, Ollama)
Start Docker Desktop, then:
```bash
cd ai-backend && docker compose up -d
```

### 2. Install dependencies (already done)
- **ai-backend:** `cd ai-backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- **frontend:** `cd frontend && npm install`

### 3. Run DB migrations (after Docker is up)
```bash
./run-migrations.sh
```

### 4. Run servers
- **AI backend (port 8001):** `cd ai-backend && source .venv/bin/activate && python structure_api.py`
- **Frontend (port 5173):** `cd frontend && npm run dev`

Open http://localhost:5173 for the app. Ensure `ai-backend/.env` has `GOOGLE_API_KEY` set for structure AI.
