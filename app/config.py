from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr, model_validator


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str
    REDIS_POOL_MAX: int = 20

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    API_BASE_URL: str = "http://localhost:8000"

    # SendGrid
    SENDGRID_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@yourapp.com"
    EMAIL_FROM_NAME: str = "RAG System"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str | None = None
    MINIO_SECRET_KEY: str | None = None
    MINIO_BUCKET: str = "rag-docs"
    MINIO_SECURE: bool = False

    # ChromaDB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001

    # OpenRouter (LLM)
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = "openrouter/elephant-alpha"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 2048

    # OpenAI (Embeddings)
    EMBED_MODEL: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    EMBED_DIMENSIONS: int = 1536

    # Jina (Reranker)
    JINA_API_KEY: str = ""
    JINA_RERANKER_MODEL: str = "jina-reranker-v2-base-multilingual"
    JINA_RERANKER_TOP_N: int = 5

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_DAY: int = 1000

    # App
    FRONTEND_URL: str = "http://localhost:3000"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def check_minio_credentials(self):
        if self.ENVIRONMENT == "production":
            if not self.MINIO_ACCESS_KEY or not self.MINIO_SECRET_KEY:
                raise ValueError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set in production")
        else:
            if not self.MINIO_ACCESS_KEY:
                self.MINIO_ACCESS_KEY = "minioadmin"
            if not self.MINIO_SECRET_KEY:
                self.MINIO_SECRET_KEY = "minioadmin"
        return self


settings = Settings()
