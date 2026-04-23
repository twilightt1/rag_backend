from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr, model_validator


class Settings(BaseSettings):
              
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

           
    REDIS_URL: str
    REDIS_POOL_MAX: int = 20

         
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

                  
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    API_BASE_URL: str = "http://localhost:8000"

              
    SENDGRID_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@yourapp.com"
    EMAIL_FROM_NAME: str = "RAG System"

           
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str | None = None
    MINIO_SECRET_KEY: str | None = None
    MINIO_BUCKET: str = "rag-docs"
    MINIO_SECURE: bool = False

              
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001

                      
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = "openai/gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 2048



    OPENAI_API_KEY: str = ""
    EMBED_MODEL: str = "text-embedding-3-small"
    EMBED_DIMENSIONS: int = 1536

                     
    JINA_API_KEY: str = ""
    JINA_RERANKER_MODEL: str = "jina-reranker-v2-base-multilingual"
    JINA_RERANKER_TOP_N: int = 5

            
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

                   
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_DAY: int = 1000

         
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
