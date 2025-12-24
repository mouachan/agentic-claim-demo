"""
Configuration settings for the Claims Demo backend application.
Loads settings from environment variables and provides typed configuration.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Claims Processing Demo"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = "production"

    # API
    api_v1_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database
    postgres_host: str = "postgresql-service"
    postgres_port: int = 5432
    postgres_db: str = "claims_db"
    postgres_user: str
    postgres_password: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL database URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """Construct async PostgreSQL database URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # LlamaStack (OpenShift AI)
    llamastack_endpoint: str = "http://claims-llamastack.claims-demo.svc.cluster.local:8080"
    llamastack_api_key: Optional[str] = None
    llamastack_default_model: str = "llama-3.1-8b-instruct"
    llamastack_embedding_model: str = "sentence-transformers/all-mpnet-base-v2"
    llamastack_embedding_dimension: int = 768
    llamastack_timeout: int = 300  # seconds
    llamastack_max_retries: int = 3

    # MCP Servers
    ocr_server_url: str = "http://ocr-server.claims-demo.svc.cluster.local:8080"
    rag_server_url: str = "http://rag-server.claims-demo.svc.cluster.local:8080"
    orchestrator_server_url: str = (
        "http://orchestrator-server.claims-demo.svc.cluster.local:8080"
    )
    guardrails_server_url: str = (
        "http://claims-guardrails.claims-demo.svc.cluster.local:8080"
    )

    # CORS
    cors_origins: list[str] = ["*"]  # In production, specify actual origins
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]

    # Security
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # File Storage
    documents_storage_path: str = "/mnt/documents"
    max_upload_size_mb: int = 10

    # Processing
    max_processing_time_seconds: int = 300
    default_workflow_type: str = "standard"
    enable_async_processing: bool = True

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 9090

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
settings = Settings()
