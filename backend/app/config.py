from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Final-hardening-phase startup guard (Part 3A): these are the literal
# placeholder values shipped in `.env.example` and used as field defaults
# below. Kept here, not just as the field defaults, so the guard below
# compares against the EXACT known-unsafe strings rather than re-deriving
# them - if either literal ever changes, this dict must change with it,
# which is the point (a silent drift would silently weaken the guard).
_PLACEHOLDER_SECRET_DEFAULTS = {
    "SESSION_SECRET": "change-me-32-bytes-minimum-session-secret-key",
    "DEMO_RESET_SECRET": "change-me-demo-reset-secret",
}

# Environments where these placeholders are expected and safe: local
# developer machines and CI runners never expose these endpoints to the
# public internet, and every existing test/dev workflow in this repository
# already relies on APP_ENV defaulting to "local" with no `.env` file
# present. Any OTHER value (e.g. "demo", or a future real deployment
# environment) is treated as "not provably safe" and must supply real
# secrets - see `_reject_placeholder_secrets_outside_local_or_ci` below.
_ENVS_WHERE_PLACEHOLDERS_ARE_ALLOWED = {"local", "ci"}


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
    AI_PROVIDER: str = "mock"  # mock | llm | local_ml
    AI_TIMEOUT_SECONDS: int = 4
    AI_API_KEY: str = ""
    AI_MODEL: str = ""
    # Empty -> LLMProvider's own default (https://api.openai.com/v1). Set this
    # to a local inference server's OpenAI-compatible base (e.g. Ollama's
    # "http://localhost:11434/v1") to run an open-source model with no API
    # key at all - LLMProvider only sends an Authorization header when
    # AI_API_KEY is non-empty, which real local servers like Ollama ignore.
    AI_BASE_URL: str = ""
    EVIDENCE_STORAGE_DIR: str = "./storage/evidence"
    EVIDENCE_MAX_BYTES: int = 10485760  # 10 MB
    DEMO_RESET_SECRET: str = "change-me-demo-reset-secret"
    LOG_LEVEL: str = "INFO"
    GIT_SHA: str = "dev"

    @model_validator(mode="after")
    def _reject_placeholder_secrets_outside_local_or_ci(self) -> "Settings":
        """Startup guard (final-hardening phase, Part 3A).

        `SESSION_SECRET` signs every session cookie (`app/security/session.py`)
        and `DEMO_RESET_SECRET` gates the destructive `/demo/reset` endpoint
        (`app/api/v1/demo.py`). Both ship with well-known placeholder values
        so `local`/`ci` stay usable with zero configuration - but if either
        one is STILL a placeholder in any other `APP_ENV` (e.g. a real
        "demo" deployment reachable outside this machine), every session
        cookie is forgeable and the demo-reset endpoint is guessable by
        anyone who has read this file. Refusing to start is strictly safer
        than starting insecurely: `demo`/other environments remain fully
        usable, they just must supply real secrets (via env vars or a real
        `.env`), exactly as `.env.example` already instructs. The message
        names which settings are unset, never their values.
        """
        if self.APP_ENV in _ENVS_WHERE_PLACEHOLDERS_ARE_ALLOWED:
            return self
        still_placeholder = [
            name
            for name, placeholder in _PLACEHOLDER_SECRET_DEFAULTS.items()
            if getattr(self, name) == placeholder
        ]
        if still_placeholder:
            joined = ", ".join(still_placeholder)
            raise ValueError(
                f"Refusing to start with APP_ENV={self.APP_ENV!r}: {joined} "
                f"{'is' if len(still_placeholder) == 1 else 'are'} still set to "
                "the known placeholder default from .env.example. Set a real, "
                "unique value via environment variable or .env before starting "
                "outside local/ci."
            )
        return self


settings = Settings()
