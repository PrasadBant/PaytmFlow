"""Integration tests for the /translate endpoint (Sarvam Mayura).

Translation is scoped to ONE already-generated free-text string per call -
these tests confirm the endpoint never touches numbers/statuses (that
guarantee lives in the frontend calling this per-string, not per-response;
here we confirm the endpoint's own contract: text in, text out, nothing
else silently mutated) and degrades cleanly when disabled/misconfigured.
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from app.ai.sarvam import SarvamProvider
from app.ai.sarvam_client import SarvamTimeoutError
from app.config import settings


def _enable_sarvam_translation(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_TRANSLATION_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "sarvam")


class TestTranslate:
    async def test_translation_disabled_returns_404(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "SARVAM_ENABLED", False)
        resp = await client.post(
            "/api/v1/translate",
            json={"text": "Your income proof needs review.", "target_language_code": "hi-IN"},
            headers=session_headers,
        )
        assert resp.status_code == 404

    async def test_translation_requires_sarvam_provider(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
        monkeypatch.setattr(settings, "SARVAM_TRANSLATION_ENABLED", True)
        monkeypatch.setattr(settings, "AI_PROVIDER", "mock")
        resp = await client.post(
            "/api/v1/translate",
            json={"text": "Your income proof needs review.", "target_language_code": "hi-IN"},
            headers=session_headers,
        )
        assert resp.status_code == 404

    async def test_translation_timeout_returns_504(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        _enable_sarvam_translation(monkeypatch)
        with patch.object(
            SarvamProvider,
            "translate_text",
            new=AsyncMock(side_effect=SarvamTimeoutError("timeout")),
        ):
            resp = await client.post(
                "/api/v1/translate",
                json={"text": "Your income proof needs review.", "target_language_code": "hi-IN"},
                headers=session_headers,
            )
        assert resp.status_code == 504

    async def test_translation_success_preserves_text_boundary(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        """The endpoint returns exactly what the provider translated - no
        amounts/statuses live in this call at all, since the frontend only
        ever sends one free-text explanation string, never a whole payload."""
        _enable_sarvam_translation(monkeypatch)
        original = "Your income proof of ₹50,000 needs additional review."
        with patch.object(
            SarvamProvider,
            "translate_text",
            new=AsyncMock(return_value="आपके ₹50,000 के आय प्रमाण की अतिरिक्त समीक्षा आवश्यक है।"),
        ):
            resp = await client.post(
                "/api/v1/translate",
                json={"text": original, "target_language_code": "hi-IN"},
                headers=session_headers,
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "₹50,000" in body["translated_text"]
        assert body["translated_text"] != original
