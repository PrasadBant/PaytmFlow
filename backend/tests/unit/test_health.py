import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["ok", "degraded"]
        assert "db" in data
        assert "packs_loaded" in data
        assert "ai_provider" in data
        # "local_ml" is a real, fully-supported AI_PROVIDER value (the real
        # local Document AI pipeline, app/ai/local_ml.py) - not just "mock"
        # or "llm". Regression for a real bug (final QA phase): GET /health
        # 500'd whenever the app was started with AI_PROVIDER=local_ml,
        # because HealthResponse.ai_provider's Literal only allowed
        # "mock"/"llm", found by actually starting the app that way.
        assert data["ai_provider"] in ["mock", "llm", "local_ml"]


@pytest.mark.asyncio
async def test_health_endpoint_with_local_ml_provider(monkeypatch: pytest.MonkeyPatch):
    """Direct regression test for the found bug: GET /health must not 500
    when AI_PROVIDER=local_ml - the actual real-Document-AI production
    configuration this whole project's mission is built around."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200, response.text
        assert response.json()["ai_provider"] == "local_ml"
