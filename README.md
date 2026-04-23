# 🚀 Hệ Thống RAG(RAG System)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=for-the-badge&logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/LangGraph-Stateful-orange?style=for-the-badge&logo=langchain" alt="LangGraph" />
  <img src="https://img.shields.io/badge/ChromaDB-Vector_Store-lightgrey?style=for-the-badge" alt="ChromaDB" />
  <img src="https://img.shields.io/badge/Docker-Infrastructure-2496ED?style=for-the-badge&logo=docker" alt="Docker" />
</p>

---

## 🌟 Tổng Quan

Một hệ thống backend **RAG (Retrieval-Augmented Generation)** với hiệu suất cao. Backend này sử dụng **LangGraph** để điều phối các luồng dữ liệu phức tạp, đảm bảo độ chính xác cao trong việc truy xuất, xếp hạng lại (reranking) tinh vi, và định tuyến linh hoạt các truy vấn của người dùng.

Được thiết kế để có khả năng mở rộng và hiệu suất ở cấp độ sản phẩm thực tế (production-grade), hệ thống tích hợp tìm kiếm lai (hybrid search), bộ nhớ thông minh và phản hồi dạng luồng (streaming) qua SSE.

---

## ✨ Các Tính Năng Chính

| Tính Năng | Mô Tả |
| :--- | :--- |
| **🤖 Luồng Làm Việc** | Điều phối nhiều bước, có trạng thái sử dụng LangGraph (Tác tử Định tuyến, Đánh giá, Ảo giác, v.v.). |
| **🧭 Định Tuyến Động** | Phân loại thông minh các truy vấn thành `rag` (truy xuất), `chitchat` (trò chuyện), `summarize` (tóm tắt), hoặc `clarify` (làm rõ). |
| **🔍 Tìm Kiếm Lai** | Kết hợp Tìm kiếm Ngữ nghĩa **Vector** (ChromaDB) với tìm kiếm từ vựng **BM25** thông qua RRF. |
| **🎯 Xếp Hạng Lại (Reranking) Nâng Cao** | Tinh chỉnh cross-encoder sử dụng **Jina AI Reranker** để đạt độ chính xác hàng đầu. |
| **🧠 Bộ Nhớ Thông Minh** | Đảm bảo tính nhất mạch trong hội thoại nhiều lượt thông qua quản lý lịch sử có trạng thái. |
| **🔄 Tự Sửa Lỗi** | Đánh giá tính ảo giác và mức độ liên quan với khả năng tự động truy xuất lại. |
| **🚀 Sẵn Sàng Cho Production** | Bộ đệm Redis, các tác vụ nền Celery, và lưu trữ MinIO. |

---

## 🛠️ Công Nghệ Sử Dụng

- **Khung Cốt Lõi (Framework)**: [FastAPI](https://fastapi.tiangolo.com/)
- **Điều Phối (Orchestration)**: [LangGraph](https://python.langchain.com/docs/langgraph) / [LangChain](https://python.langchain.com/)
- **Cơ Sở Dữ Liệu Vector**: [ChromaDB](https://www.trychroma.com/)
- **Xếp Hạng Lại (Reranker)**: [Jina AI](https://jina.ai/)
- **Nhúng (Embedder)**: Text 3 Small (OpenAI)
- **Cơ Sở Dữ Liệu**: [PostgreSQL](https://www.postgresql.org/) với SQLAlchemy (Bất đồng bộ)
- **Lưu Trữ Đối Tượng (Object Storage)**: [MinIO](https://min.io/) (Tương thích S3)
- **Bộ Nhớ Đệm & Tác Vụ**: [Redis](https://redis.io/) & [Celery](https://docs.celeryq.dev/)
- **Cổng LLM (LLM Gateway)**: [OpenRouter](https://openrouter.ai/)

---

## 📈 Kiến Trúc Hệ Thống

```mermaid
graph TD
    User([Truy Vấn Người Dùng]) --> Rewriter[Viết Lại Truy Vấn]
    Rewriter --> Router{Tác Tử Định Tuyến}
    
    Router -- rag/summarize --> Memory[Tác Tử Bộ Nhớ]
    Router -- chitchat --> Answer[Tác Tử Trả Lời]
    Router -- clarify --> Clarify[Nút Làm Rõ]
    
    Memory --> Retrieval[Tác Tử Truy Xuất]
    Retrieval --> Evaluator[Tác Tử Đánh Giá]
    
    Evaluator -- không liên quan --> Retrieval
    Evaluator -- có liên quan --> Answer
    
    Answer --> Hallucination[Tác Tử Ảo Giác]
    Hallucination -- có ảo giác --> Retrieval
    Hallucination -- dựa trên thực tế --> Save[Tác Tử Lưu Trữ]
    
    Clarify --> Save
    Save --> End([Luồng Phản Hồi])
    
    subgraph "Tìm Kiếm Lai"
    Retrieval -.-> Vector[Lưu Trữ Vector]
    Retrieval -.-> BM25[Tìm Kiếm Từ Vựng]
    end
```

---

## 🚀 Bắt Đầu

### 1. Yêu Cầu Cần Thiết
- Python 3.10+
- Docker & Docker Compose

### 2. Thiết Lập & Cài Đặt
```bash
# Clone kho lưu trữ
git clone <repository-url>
cd rag-backend

# Khởi tạo Môi trường Ảo (Virtual Environment)
python -m venv venv
source venv/bin/activate  # Trên Windows: venv\Scripts\activate

# Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt
```

### 3. Khởi Chạy Cơ Sở Hạ Tầng
Khởi động các dịch vụ cần thiết (MinIO, Redis, PostgreSQL, ChromaDB) chỉ bằng một lệnh:
```bash
docker-compose up -d
```

---

## ⚙️ Cấu Hình

Tạo tệp `.env` trong thư mục gốc:

```env
# 🐘 Cơ Sở Dữ Liệu
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/ragdb

# 🔴 Bộ Đệm & Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# 🤖 LLM (OpenRouter)
OPENROUTER_API_KEY=your_openrouter_key
LLM_MODEL=openai/gpt-4o-mini

# 🎯 Jina Reranker
JINA_API_KEY=your_jina_key

# 📦 Lưu Trữ (MinIO)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=rag-docs

# 🔎 Cơ Sở Dữ Liệu Vector (ChromaDB)
CHROMA_HOST=localhost
CHROMA_PORT=8001

# 🔑 Xác Thực
JWT_SECRET_KEY=your_very_secret_key
GOOGLE_CLIENT_ID=your_google_id
GOOGLE_CLIENT_SECRET=your_google_secret
```

---

## 🛤️ Các API Endpoint

| Phương Thức | Endpoint | Mô Tả |
| :--- | :--- | :--- |
| `POST` | `/api/v1/chat/completions` | Điểm vào chính của RAG/Chat (Hỗ trợ Streaming) |
| `POST` | `/api/v1/documents/upload` | Nhập tài liệu và nhúng (embedding) |
| `GET` | `/api/v1/conversations` | Truy xuất lịch sử hội thoại |
| `GET` | `/health` | Kiểm tra tình trạng hệ thống |

---

## 🔍 Khả Năng Theo Dõi Tác Tử

Mỗi phản hồi đều bao gồm một đối tượng siêu dữ liệu `agent_trace`. Điều này cung cấp khả năng hiển thị sâu vào:
- **Các Quyết Định Định Tuyến**: Tại sao một luồng cụ thể được chọn.
- **Số Liệu Truy Xuất**: Điểm số từ tìm kiếm Vector và BM25.
- **Logic Xếp Hạng Lại**: Cách ưu tiên ngữ cảnh cuối cùng.

---

<p align="center">
  Được xây dựng với ❤️ dành cho Các Ứng Dụng AI Hiệu Suất Cao
</p>