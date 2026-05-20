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

Copy the example file and add your OpenRouter key:

```bash
cp .env.example .env
```

Minimum required in `.env`:

```bash
OPENAI_API_KEY=your_openrouter_key
```

See `.env.example` for all optional settings (models, timeouts, cache, external risk APIs).

The backend validates required settings on startup. If `OPENAI_API_KEY` is missing,
the API exits with a clear configuration error.

Useful security/runtime settings:

- `MAX_UPLOAD_SIZE_MB` controls the maximum accepted PDF size (default: 25 MB).
- `CORS_ORIGINS` is a comma-separated allowlist for browser clients, for example:
  `http://127.0.0.1:5500,http://localhost:5500`.

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
pytest
```

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
cp .env.example .env
# edit .env and set OPENAI_API_KEY
docker compose up --build
```

Then open:

- Frontend: `http://127.0.0.1:5500/`
- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

The compose file mounts local `data/` and `db/` folders so uploaded PDFs and FAISS indexes persist across container restarts.

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

- Hybrid retrieval (vector + keyword search)
- React-based frontend
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
