<img width="100" height="104" alt="RAG" src="https://github.com/user-attachments/assets/9a1d375b-1286-4ae2-901c-238a11ad8aab" />

# 🚀 DocFlow RAG System

An Agentic Retrieval-Augmented Generation (RAG) System that allows users to upload documents, query them, and receive not just answers—but multi-agent supply chain intelligence with risk levels, recommendations, and final decision support.

---

## 🧠 Key Idea

Traditional RAG systems only return answers.

👉 DocFlow goes beyond that by adding a RiskWise-style Multi-Agent Layer that analyzes retrieved information from multiple business perspectives:

- 🏭 Supplier Risk
- 📦 Inventory Risk
- 🚚 Logistics Risk
- 🌍 External Risk
- 🎯 Final Decision Recommendation

---

## 🏗️ Architecture

Frontend (HTML/JS UI)  
↓ FastAPI Backend  
↓ RAG Pipeline (FAISS + OpenRouter Embeddings)  
↓ LLM Answer Generation (OpenRouter)  
↓ Multi-Agent Analysis Layer  
↓ Final Decision Agent

---

## ⚙️ Features

### 📄 Document Ingestion

- Upload PDF documents
- Automatic text extraction and chunking
- Embedding generation using OpenRouter
- Storage in FAISS vector database
- Incremental ingestion skips unchanged PDFs and appends only new or changed files

### 🔎 Intelligent Querying

- Semantic search over documents
- Context-aware answers using LLM
- Source attribution for transparency

### 🤖 Multi-Agent Layer (Core Innovation)

- Converts retrieved answers into structured supply-chain intelligence:
  - Supplier Agent
  - Inventory Agent
  - Logistics Agent
  - External Risk Agent
  - Decision Agent
- Each domain agent returns:
  - Risk Level (Low / Medium / High)
  - Reason
  - Recommended Action
- The Decision Agent combines all outputs into:
  - Final Risk
  - Final Decision
  - Priority Action

### 🌐 API Backend

- Built with FastAPI
- Endpoints:
  - POST /upload → Upload and process documents
  - POST /query → Ask questions and get structured responses
  - GET /health → API liveness check (includes `version`, `vector_db_ready`)
  - GET /stats → Cache stats, query count, uptime, and `version`
  - GET /documents → List indexed PDF filenames in `data/`
  - POST /cache/clear → Clear the in-memory query cache
- Request timing middleware (X-Response-Time header)
- Slow-request logging (>5 s)
- Production-safe error responses (no internal stack traces leaked)
- Startup validates required OpenRouter configuration
- `/query` returns HTTP 503 until a FAISS vector database exists

### 💻 Frontend UI

- Upload documents
- Ask questions
- View:
  - Answer
  - Multi-Agent Intelligence
  - Final Decision
  - Sources
- Session dashboard:
  - Total queries
  - Low / Medium / High risk counts
  - Reset dashboard control
- Response time display per query
- Persistent query history (localStorage) with risk badges and re-run on click

---

## 🛠️ Tech Stack

- Backend: FastAPI
- LLM & Embeddings: OpenRouter (OpenAI-compatible API)
- Vector DB: FAISS
- Framework: LangChain
- Frontend: HTML, CSS, JavaScript

---

## 📦 Installation

```bash
git clone https://github.com/anuragthippani1/DocFlow-RAG.git
cd DocFlow-RAG

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

---

## 🔐 Environment Variables

Create a local `.env` file in the project root (never commit it). Minimum required:

```bash
OPENAI_API_KEY=your_openrouter_key
```

The backend validates required settings on startup. If `OPENAI_API_KEY` is missing,
the API exits with a clear configuration error.

Common optional settings:

- `OPENAI_API_BASE` — default `https://openrouter.ai/api/v1`
- `EMBEDDING_MODEL`, `QA_MODEL`, `AGENT_MODEL` — model names
- `MAX_UPLOAD_SIZE_MB` — max PDF size (default: 25 MB)
- `CORS_ORIGINS` — comma-separated browser origins, e.g. `http://127.0.0.1:5500,http://localhost:5500`
- `API_KEY` — require `X-API-Key` on protected routes
- `HYBRID_RETRIEVAL_ENABLED`, `RERANK_ENABLED` — advanced retrieval
- `CELERY_ENABLED`, `REDIS_URL` — background ingestion

---

## ▶️ Run the Project

### Start Backend Locally

```bash
./venv/bin/python -m uvicorn app.main:app --reload
```

### Open API Docs

`http://127.0.0.1:8000/docs`

### Run Tests

```bash
python -m pytest
```

CI runs the same command on every push to `main` (see `.github/workflows/main.yml`).

### Start Frontend

Serve the static UI (required for API calls — `file://` is blocked by the browser):

```bash
cd frontend
python3 -m http.server 5500
```

Open: `http://127.0.0.1:5500/`

### Docker Setup

Build and run the API plus static frontend:

```bash
# create .env locally with OPENAI_API_KEY (do not commit)
docker compose up --build
```

Then open:

- Frontend: `http://127.0.0.1:5500/`
- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

The compose file mounts local `data/` and `db/` folders so uploaded PDFs and FAISS indexes persist across container restarts.

### API Security

Set `API_KEY` in `.env` to require the `X-API-Key` header on `/upload`, `/query`, and `/documents` routes.
The frontend stores the key in browser localStorage.

### Hybrid Retrieval and Reranking

Enable in `.env`:

```bash
HYBRID_RETRIEVAL_ENABLED=true
RERANK_ENABLED=true
```

Requires `rank-bm25` and `sentence-transformers` (see `requirements.txt`).

### LangSmith Tracing

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_PROJECT=docflow-rag
```

### Evaluation Harness

```bash
python -m evaluation.runner
```

Writes `evaluation/reports/latest.json` with Precision@K, Recall@K, MRR, and RAG triad scores.

### Distributed Ingestion (Celery)

```bash
CELERY_ENABLED=true
docker compose up --build
```

Uploads are queued to the `worker` service when Celery is enabled.

### Deploy on Render

Render is a good fit for the **API** (Docker + persistent disk) and the **static frontend**.

#### One-click Blueprint

1. Push this repo to GitHub (already connected if you cloned from there).
2. In [Render](https://render.com) → **New** → **Blueprint**.
3. Select the repo — Render reads `render.yaml` and creates:
   - **docflow-api** — Docker Web Service (port 8000, health `/health`, 1 GB disk at `/var/data`)
   - **docflow-ui** — Static site from `frontend/`
4. Set **OPENAI_API_KEY** when prompted (required).
5. After deploy, on **docflow-api** → **Environment**, set:
   ```bash
   CORS_ORIGINS=https://docflow-ui.onrender.com
   ```
   Add other origins (e.g. Vercel) comma-separated if needed.
6. Open **docflow-ui** → **API Settings** (auto-fills API URL when using default Blueprint names):
   - **API URL:** `https://docflow-api.onrender.com` (your API service URL)
   - **API Key:** copy from **docflow-api** env `API_KEY` (auto-generated by Blueprint)

#### Manual setup (alternative)

| Service | Type | Settings |
|---------|------|----------|
| API | Web Service → Docker | Dockerfile `./Dockerfile`, port `8000`, health `/health` |
| UI | Static Site | Root `frontend`, publish `.` |

Mount a **persistent disk** on the API service (paid plan):

| Mount path | Env |
|------------|-----|
| `/var/data` | `DATA_PATH=/var/data/data`, `DB_PATH=/var/data/db` |

Required API env vars: `OPENAI_API_KEY`, `API_KEY` (recommended), `CORS_ORIGINS` (your UI URL).

#### Notes

- **Free tier** API sleeps after idle; first request may be slow. Disk persistence needs **Starter** or higher.
- **Vercel + Render:** host UI on Vercel, API on Render — set `CORS_ORIGINS` to your Vercel URL and API URL in the UI settings.
- Skip Celery on first deploy (`CELERY_ENABLED=false`).

---

## 🧪 Example Query

What problem does GRAIL solve?

### Output

- Answer from documents
- Supplier / Inventory / Logistics / External Risk agent outputs
- Final Decision with priority action
- Source references

---

## 🚀 Future Improvements

- React-based frontend (current UI is modular vanilla JS)
- Persistent query analytics dashboard
- Exportable PDF/JSON risk reports
- Authentication and team workspaces

---

## 🎯 Why This Project Stands Out

- Not just a chatbot → decision-oriented AI system
- Combines:
  - Retrieval
  - LLM reasoning
  - Agent-based analysis
- Designed like real-world AI systems
