"""Startup validation of the n8n outbox settings (app/config.py): production
must not silently pick a retention period, and bad values are refused."""

import pytest
from pydantic import ValidationError

from app.config import Settings

PROD = {
    "APP_ENV": "production",
    "SESSION_SECRET": "test-only-session-secret-0123456789abcdef",
    "DEMO_RESET_SECRET": "test-only-demo-reset-secret-0123456789",
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "APP_ENV",
        "N8N_ENABLED",
        "N8N_FAILURE_RETENTION_DAYS",
        "N8N_OUTBOX_LEASE_SECONDS",
        "N8N_OUTBOX_SWEEP_SECONDS",
        "N8N_OUTBOX_MAX_ATTEMPTS",
        "N8N_FLUSH_BUDGET_SECONDS",
        "N8N_TIMEOUT_SECONDS",
        "SESSION_SECRET",
        "DEMO_RESET_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_production_with_n8n_enabled_refuses_to_start_without_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, **PROD, N8N_ENABLED="true")
    message = str(exc.value)
    assert "N8N_FAILURE_RETENTION_DAYS is not set" in message
    assert "test-only" not in message  # names settings, never values


def test_production_with_retention_set_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, **PROD, N8N_ENABLED="true", N8N_FAILURE_RETENTION_DAYS="45")
    assert s.N8N_FAILURE_RETENTION_DAYS == 45


def test_production_with_n8n_disabled_does_not_need_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _settings(monkeypatch, **PROD).N8N_FAILURE_RETENTION_DAYS is None


@pytest.mark.parametrize("app_env", ["local", "ci"])
def test_local_and_ci_have_no_retention_default_and_still_start(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    s = _settings(monkeypatch, APP_ENV=app_env, N8N_ENABLED="true")
    assert s.N8N_FAILURE_RETENTION_DAYS is None  # = no cleanup, not an invented period


@pytest.mark.parametrize("value", ["0", "-3", "abc", "1.5"])
def test_invalid_retention_values_are_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, APP_ENV="local", N8N_FAILURE_RETENTION_DAYS=value)


def test_lease_must_outlast_a_request_flush(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _settings(
            monkeypatch,
            APP_ENV="local",
            N8N_OUTBOX_LEASE_SECONDS="10",
            N8N_FLUSH_BUDGET_SECONDS="8",
            N8N_TIMEOUT_SECONDS="5",
        )


@pytest.mark.parametrize(
    ("key", "value"), [("N8N_OUTBOX_SWEEP_SECONDS", "-1"), ("N8N_OUTBOX_MAX_ATTEMPTS", "0")]
)
def test_negative_sweep_or_zero_attempt_cap_is_refused(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, APP_ENV="local", **{key: value})
