"""/health reports the deployed commit and nothing sensitive."""

import pytest
from httpx import AsyncClient

from app.config import settings

SHA = "4189f19a72dde628433103d2ce52629252c280e5"
ALLOWED_KEYS = {"status", "db", "packs_loaded", "packs_supported", "ai_provider", "git_sha"}


@pytest.mark.parametrize("git_sha", [SHA, "dev", "unknown"])
async def test_health_reports_configured_commit(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, git_sha: str
) -> None:
    monkeypatch.setattr(settings, "GIT_SHA", git_sha)
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["git_sha"] == git_sha


async def test_health_exposes_no_secrets_paths_or_config(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SESSION_SECRET", "canary-session-secret-value")
    monkeypatch.setattr(settings, "REVIEWER_ACCESS_CODE", "canary-reviewer-code-value")
    r = await client.get("/api/v1/health")
    body = r.json()
    assert set(body) <= ALLOWED_KEYS
    text = r.text
    for leaked in (
        "canary-session-secret-value",
        "canary-reviewer-code-value",
        settings.DATABASE_URL,
        "postgresql",
        "\\\\",
        "/app/",
        "/opt/",
    ):
        assert leaked not in text
