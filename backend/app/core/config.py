import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """TraceHeal Global System Configuration."""
    
    app_name: str = "TraceHeal Autonomous SRE"
    app_version: str = "1.0.0"
    env: str = "development"
    debug: bool = True
    
    # Server Binding
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    
    # Database Configuration (Async SQLite default with WAL, /tmp for Vercel)
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "sqlite+aiosqlite:////tmp/traceheal.db" if os.environ.get("VERCEL") else "sqlite+aiosqlite:///./traceheal.db"
    )
    
    # Target Microservices URLs
    gateway_service_url: str = "http://127.0.0.1:8080"
    order_service_url: str = "http://127.0.0.1:8081"
    payment_service_url: str = "http://127.0.0.1:8082"
    inventory_service_url: str = "http://127.0.0.1:8083"
    auth_service_url: str = "http://127.0.0.1:8084"
    notification_service_url: str = "http://127.0.0.1:8085"
    
    # Sandbox Settings
    sandbox_base_port: int = 9100
    sandbox_timeout_seconds: int = 30
    
    # LLM & Multi-Model AI Settings
    llm_provider: str = "gemini"  # "gemini", "openai", "anthropic", "mock"
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-1.5-flash"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # Enterprise Security & RBAC
    jwt_secret_key: str = "traceheal-enterprise-sec-key-32bytes-min"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440
    auth_strict_mode: bool = False

    # External Integrations (GitHub, Slack, Cloud)
    github_token: Optional[str] = None
    github_repo: Optional[str] = "pyharshcodes/Bharat_Agentic_2026_Hackathon"
    slack_webhook_url: Optional[str] = None
    supabase_url: Optional[str] = None

    # Infrastructure, Automation & Sandboxing
    docker_sandbox_enabled: bool = True
    auto_detector_enabled: bool = True
    continuous_traffic_enabled: bool = False

    # CORS Configuration
    cors_origins: list[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    cors_origin_regex: Optional[str] = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    model_config = SettingsConfigDict(
        env_prefix="TRACEHEAL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
