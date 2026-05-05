<img width="1024" height="1024" alt="RAG" src="https://github.com/user-attachments/assets/9a1d375b-1286-4ae2-901c-238a11ad8aab" />

# 🚀 DocFlow RAG System

An Agentic Retrieval-Augmented Generation (RAG) System that allows users to upload documents, query them, and receive not just answers—but structured insights including risk levels and recommendations.

---

## 🧠 Key Idea

Traditional RAG systems only return answers.

👉 DocFlow goes beyond that by adding an Agent Layer that analyzes retrieved information and generates:

- 📌 Summary
- 🔍 Key Insight
- ⚠️ Risk Level
- 💡 Recommendation

---

## 🏗️ Architecture

Frontend (HTML/JS UI)  
↓ FastAPI Backend  
↓ RAG Pipeline (FAISS + Embeddings)  
↓ LLM (OpenRouter)  
↓ Agent Layer (Analysis + Decision)

---

## ⚙️ Features

### 📄 Document Ingestion

- Upload PDF documents
- Automatic text extraction and chunking
- Embedding generation using OpenRouter
- Storage in FAISS vector database

### 🔎 Intelligent Querying

- Semantic search over documents
- Context-aware answers using LLM
- Source attribution for transparency

### 🤖 Agent Layer (Core Innovation)

- Converts answers into structured insights:
  - Summary
  - Key Insight
  - Risk Level (Low / Medium / High)
  - Actionable Recommendation

### 🌐 API Backend

- Built with FastAPI
- Endpoints:
  - POST /upload → Upload and process documents
  - POST /query → Ask questions and get structured responses

### 💻 Frontend UI

- Upload documents
- Ask questions
- View:
  - Answer
  - Agent Analysis
  - Sources

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
git clone https://github.com/YOUR_USERNAME/DocFlow-RAG.git
cd DocFlow-RAG

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

---

## 🔐 Environment Variables

Create a `.env` file:

```bash
OPENAI_API_KEY=your_openrouter_key
OPENAI_API_BASE=https://openrouter.ai/api/v1
OPENROUTER_SITE_URL=http://localhost
OPENROUTER_APP_NAME=DocFlow-RAG
```

---

## ▶️ Run the Project

### Start Backend

```bash
uvicorn app.main:app --reload
```

### Open API Docs

`http://127.0.0.1:8000/docs`

### Open Frontend

Open:

`frontend/index.html`

---

## 🧪 Example Query

What problem does GRAIL solve?

### Output

- Answer from documents
- Agent Analysis (summary, insight, risk, recommendation)
- Source references

---

## 🚀 Future Improvements

- Multi-agent system (Supplier, Risk, Inventory agents)
- Hybrid retrieval (vector + keyword search)
- React-based frontend
- Evaluation dashboard for RAG performance

---

## 🎯 Why This Project Stands Out

- Not just a chatbot → decision-oriented AI system
- Combines:
  - Retrieval
  - LLM reasoning
  - Agent-based analysis
- Designed like real-world AI systems
