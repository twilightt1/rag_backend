# 🚀 Multi-Agentic RAG System

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=for-the-badge&logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/LangGraph-Stateful-orange?style=for-the-badge&logo=langchain" alt="LangGraph" />
  <img src="https://img.shields.io/badge/ChromaDB-Vector_Store-lightgrey?style=for-the-badge" alt="ChromaDB" />
  <img src="https://img.shields.io/badge/Docker-Infrastructure-2496ED?style=for-the-badge&logo=docker" alt="Docker" />
</p>

---

## 🌟 Overview

A high-performance, **state-of-the-art Multi-Agentic RAG (Retrieval-Augmented Generation) system**. This backend leverages **LangGraph** to orchestrate complex data flows, ensuring high precision in retrieval, sophisticated reranking, and dynamic routing of user queries.

Designed for scalability and production-grade performance, it integrates hybrid search, intelligent memory, and streaming responses via SSE.

---

## ✨ Key Features

| Feature | Description |
| :--- | :--- |
| **🤖 Multi-Agent Workflow** | Stateful, multi-step orchestration using LangGraph (Router, Evaluator, Hallucination, etc.). |
| **🧭 Dynamic Routing** | Smart classification of queries into `rag`, `chitchat`, `summarize`, or `clarify`. |
| **🔍 Hybrid Retrieval** | Merges semantic **Vector Search** (ChromaDB) with lexical **BM25** via RRF. |
| **🎯 Advanced Reranking** | Cross-encoder refinement using **Jina AI Reranker** for top-tier precision. |
| **🧠 Intelligent Memory** | Multi-turn dialogue coherence through stateful history management. |
| **🔄 Self-Correction** | Hallucination and relevance grading with automatic re-retrieval. |
| **🚀 Production Ready** | Redis caching, Celery background tasks, and MinIO storage. |

---

## 🛠️ Tech Stack

- **Core Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Orchestration**: [LangGraph](https://python.langchain.com/docs/langgraph) / [LangChain](https://python.langchain.com/)
- **Vector DB**: [ChromaDB](https://www.trychroma.com/)
- **Reranker**: [Jina AI](https://jina.ai/)
- **Embedder**: NVIDIA Llama-Nemotron
- **Database**: [PostgreSQL](https://www.postgresql.org/) with SQLAlchemy (Async)
- **Object Storage**: [MinIO](https://min.io/) (S3 Compatible)
- **Cache & Tasks**: [Redis](https://redis.io/) & [Celery](https://docs.celeryq.dev/)
- **LLM Gateway**: [OpenRouter](https://openrouter.ai/)

---

## 📈 System Architecture

```mermaid
graph TD
    User([User Query]) --> Rewriter[Query Rewriter]
    Rewriter --> Router{Router Agent}
    
    Router -- rag/summarize --> Memory[Memory Agent]
    Router -- chitchat --> Answer[Answer Agent]
    Router -- clarify --> Clarify[Clarify Node]
    
    Memory --> Retrieval[Retrieval Agent]
    Retrieval --> Evaluator[Evaluator Agent]
    
    Evaluator -- irrelevant --> Retrieval
    Evaluator -- relevant --> Answer
    
    Answer --> Hallucination[Hallucination Agent]
    Hallucination -- hallucinated --> Retrieval
    Hallucination -- grounded --> Save[Save Agent]
    
    Clarify --> Save
    Save --> End([Stream Response])
    
    subgraph "Hybrid Search"
    Retrieval -.-> Vector[Vector Store]
    Retrieval -.-> BM25[Lexical Search]
    end
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- Docker & Docker Compose

### 2. Setup & Installation
```bash
# Clone the repository
git clone <repository-url>
cd rag-backend

# Initialize Virtual Environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Dependencies
pip install -r requirements.txt
```

### 3. Launch Infrastructure
Spin up the required services (MinIO, Redis, PostgreSQL, ChromaDB) with a single command:
```bash
docker-compose up -d
```

---

## ⚙️ Configuration

Create a `.env` file in the root directory:

```env
# 🐘 Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/ragdb

# 🔴 Cache & Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# 🤖 LLM (OpenRouter)
OPENROUTER_API_KEY=your_openrouter_key
LLM_MODEL=google/gemma-2-9b-it

# 🎯 Jina Reranker
JINA_API_KEY=your_jina_key

# 📦 Storage (MinIO)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=rag-docs

# 🔎 Vector Store (ChromaDB)
CHROMA_HOST=localhost
CHROMA_PORT=8001

# 🔑 Auth
JWT_SECRET_KEY=your_very_secret_key
GOOGLE_CLIENT_ID=your_google_id
GOOGLE_CLIENT_SECRET=your_google_secret
```

---

## 🛤️ API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/chat/completions` | Main RAG/Chat entrypoint (Supports Streaming) |
| `POST` | `/api/v1/documents/upload` | Document ingestion and embedding |
| `GET` | `/api/v1/conversations` | Retrieve conversation history |
| `GET` | `/health` | System health check |

---

## 🔍 Agent Traceability

Every response includes an `agent_trace` metadata object. This provides deep visibility into:
- **Routing Decisions**: Why a specific path was chosen.
- **Retrieval Metrics**: Scores from Vector and BM25 searches.
- **Reranking Logic**: How the final context was prioritized.

---

<p align="center">
  Built with ❤️ for High-Performance AI Applications
</p>
