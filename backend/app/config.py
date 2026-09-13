from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow"
    APP_ENV: str = "local"  # local | ci | demo
    SESSION_COOKIE_NAME: str = "pf_session"
    SESSION_SECRET: str = "change-me-32-bytes-minimum-session-secret-key"
    SESSION_TTL_DAYS: int = 30
    CORS_ORIGINS: str = "http://localhost:5173"
    AI_PROVIDER: str = "mock"  # mock | llm
    AI_TIMEOUT_SECONDS: int = 4
    AI_API_KEY: str = ""
    AI_MODEL: str = ""
    EVIDENCE_STORAGE_DIR: str = "./storage/evidence"
    EVIDENCE_MAX_BYTES: int = 10485760  # 10 MB
    DEMO_RESET_SECRET: str = "change-me-demo-reset-secret"
    LOG_LEVEL: str = "INFO"
    GIT_SHA: str = "dev"


settings = Settings()
