import re

from pydantic import AliasChoices, Field, field_validator, model_validator
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
    # Sarvam AI (docs.sarvam.ai) - a peer AIProvider alongside mock/llm/local_ml,
    # selected via AI_PROVIDER=sarvam. SARVAM_API_KEY is backend-only: never
    # returned in a response body, never logged, never sent to the frontend.
    SARVAM_ENABLED: bool = False
    SARVAM_API_KEY: str = ""
    SARVAM_BASE_URL: str = "https://api.sarvam.ai"
    SARVAM_DOCUMENT_ENABLED: bool = True
    SARVAM_SPEECH_ENABLED: bool = True
    SARVAM_TRANSLATION_ENABLED: bool = True
    SARVAM_CHAT_ENABLED: bool = True
    # Document AI is a real async job API (create -> poll -> download), and
    # genuinely slower than a single hosted-LLM completion - the generic
    # AI_TIMEOUT_SECONDS (4s, tuned for LLMProvider/local_ml) would starve
    # every Sarvam Document AI call before the job could ever finish, so this
    # provider gets its own, larger guardrail timeout (see app/ai/provider.py).
    SARVAM_TIMEOUT_SECONDS: int = 25
    SARVAM_POLL_INTERVAL_SECONDS: float = 1.5
    SARVAM_MAX_POLL_ATTEMPTS: int = 12
    SARVAM_STT_MODEL: str = "saaras:v3"
    # n8n Cloud outbound event notifications (Review Center lifecycle ->
    # Slack/email via the existing n8n workflow). Backend-only secret; never
    # sent to the frontend. Disabled by default so a missing/misconfigured
    # webhook can never block or fail a real journey/review-case mutation -
    # see app/integrations/n8n_client.py.
    N8N_ENABLED: bool = False
    N8N_WEBHOOK_URL: str = ""
    N8N_WEBHOOK_SECRET: str = ""
    # n8n's "Header Auth" credential type lets the workflow author configure
    # ANY header name (there is no fixed convention) - must match exactly
    # whatever header name is set on the webhook node's Header Auth
    # credential in n8n, not necessarily "Authorization".
    N8N_WEBHOOK_HEADER_NAME: str = "X-Webhook-Secret"
    N8N_TIMEOUT_SECONDS: int = 5
    # Per dispatch: HTTP tries for one event, and the base of the exponential
    # backoff between them (0.5s, 1s, ...).
    N8N_MAX_ATTEMPTS: int = 3
    N8N_RETRY_BACKOFF_SECONDS: float = 0.5
    # Total time one request may spend delivering its events after commit.
    N8N_FLUSH_BUDGET_SECONDS: float = 8.0
    # Outbox (n8n_outbox): background sweep interval for due/abandoned events
    # (0 disables the in-app sweeper), how long a claimed event is reserved for
    # one dispatcher, and the HTTP tries across all dispatches after which an
    # event is marked PERMANENT.
    N8N_OUTBOX_SWEEP_SECONDS: float = 30.0
    N8N_OUTBOX_LEASE_SECONDS: float = 60.0
    N8N_OUTBOX_MAX_ATTEMPTS: int = 30
    # Upper bound honoured for a Retry-After header from n8n.
    N8N_RETRY_AFTER_MAX_SECONDS: float = 3600.0
    # Engineering retention control for n8n_outbox rows, in days. No default:
    # the production value must be chosen by the application/data owner.
    # Required when N8N_ENABLED outside local/ci; unset elsewhere = no cleanup.
    N8N_FAILURE_RETENTION_DAYS: int | None = None
    EVIDENCE_STORAGE_DIR: str = "./storage/evidence"
    EVIDENCE_MAX_BYTES: int = 10485760  # 10 MB
    DEMO_RESET_SECRET: str = "change-me-demo-reset-secret"
    # Needed to become REVIEW_OFFICER outside local/ci; empty there = promotion refused.
    REVIEWER_ACCESS_CODE: str = ""
    # EVIDENCE actions without evidence_id trust client input; for test fixtures only.
    # None = allowed only when APP_ENV is local/ci.
    ALLOW_EVIDENCE_ACTIONS_WITHOUT_EVIDENCE: bool | None = None
    # Sliding-window limits on the paid AI endpoints (app/security/rate_limit.py).
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_CHAT_PER_MINUTE: int = 20
    RATE_LIMIT_TRANSLATE_PER_MINUTE: int = 30
    RATE_LIMIT_IP_PER_MINUTE: int = 120
    # All callers of one instance; cannot be bypassed by spoofing or new sessions.
    RATE_LIMIT_GLOBAL_PER_MINUTE: int = 600
    # Proxies in front of the API that append to X-Forwarded-For (0 = use the
    # TCP peer). Set only after confirming the platform's actual header chain.
    RATE_LIMIT_TRUSTED_PROXY_HOPS: int = 0
    # POST /review/role checks the shared reviewer access code: bound guessing.
    RATE_LIMIT_REVIEWER_ROLE_PER_MINUTE: int = 5
    RATE_LIMIT_REVIEWER_ROLE_IP_PER_MINUTE: int = 20
    RATE_LIMIT_REVIEWER_ROLE_GLOBAL_PER_MINUTE: int = 60
    LOG_LEVEL: str = "INFO"
    # Falls back to the commit Render injects into every deploy.
    GIT_SHA: str = Field(
        default="dev", validation_alias=AliasChoices("GIT_SHA", "RENDER_GIT_COMMIT")
    )

    @field_validator("GIT_SHA")
    @classmethod
    def _git_sha_is_a_commit(cls, value: str) -> str:
        # /health is public: only ever echo a commit hash, never arbitrary env text.
        # Anything else becomes "" and is labelled once APP_ENV is known (below).
        value = value.strip().lower()
        return value if re.fullmatch(r"[0-9a-f]{7,40}", value) else ""

    @model_validator(mode="after")
    def _label_missing_git_sha(self) -> "Settings":
        # "dev" only where it is true; a deployed build without commit metadata
        # says "unknown" rather than pretending to be a development build.
        if not self.GIT_SHA:
            self.GIT_SHA = (
                "dev" if self.APP_ENV in _ENVS_WHERE_PLACEHOLDERS_ARE_ALLOWED else "unknown"
            )
        return self

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

    @model_validator(mode="after")
    def _validate_n8n_outbox(self) -> "Settings":
        # Names settings only, never values. A missing retention value outside
        # local/ci is a startup failure rather than a silently chosen policy.
        days = self.N8N_FAILURE_RETENTION_DAYS
        if days is not None and days < 1:
            raise ValueError("N8N_FAILURE_RETENTION_DAYS must be a whole number of days >= 1.")
        if (
            self.N8N_ENABLED
            and days is None
            and self.APP_ENV not in _ENVS_WHERE_PLACEHOLDERS_ARE_ALLOWED
        ):
            raise ValueError(
                f"Refusing to start with APP_ENV={self.APP_ENV!r} and N8N_ENABLED=true: "
                "N8N_FAILURE_RETENTION_DAYS is not set. It controls how long n8n_outbox "
                "rows are kept; the value must be chosen by the application/data owner."
            )
        if (
            self.N8N_OUTBOX_LEASE_SECONDS
            <= self.N8N_FLUSH_BUDGET_SECONDS + self.N8N_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "N8N_OUTBOX_LEASE_SECONDS must exceed N8N_FLUSH_BUDGET_SECONDS + "
                "N8N_TIMEOUT_SECONDS, or a slow send could outlive its lease."
            )
        if self.N8N_OUTBOX_SWEEP_SECONDS < 0 or self.N8N_OUTBOX_MAX_ATTEMPTS < 1:
            raise ValueError(
                "N8N_OUTBOX_SWEEP_SECONDS must be >= 0 and N8N_OUTBOX_MAX_ATTEMPTS >= 1."
            )
        return self


settings = Settings()
