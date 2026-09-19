"""Integration tests for voice input to the customer assistant (Sarvam
Saaras speech-to-text). Voice is an input modality, not an authorization
mechanism - these tests confirm a spoken message can never bypass the
same advisory-only, grounded chat() path a typed message already uses.
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from app.ai.sarvam import SarvamProvider
from app.ai.sarvam_client import SarvamTimeoutError
from app.config import settings


async def _create_lending_journey(client: AsyncClient, headers: dict[str, str]) -> dict:
    resp = await client.post(
        "/api/v1/journeys",
        json={
            "journey_type": "LENDING",
            "goal": {"loan_amount": 200000, "loan_purpose": "EDUCATION", "tenure_months": 24},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _enable_sarvam_voice(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_SPEECH_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "sarvam")


class TestChatVoice:
    async def test_voice_disabled_returns_404(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        monkeypatch.setattr(settings, "SARVAM_ENABLED", False)

        resp = await client.post(
            f"/api/v1/journeys/{journey['journey_id']}/chat/voice",
            files={"file": ("clip.wav", b"fake-audio-bytes", "audio/wav")},
            headers=session_headers,
        )
        assert resp.status_code == 404

    async def test_voice_requires_sarvam_provider_configured(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
        monkeypatch.setattr(settings, "SARVAM_SPEECH_ENABLED", True)
        monkeypatch.setattr(settings, "AI_PROVIDER", "mock")

        resp = await client.post(
            f"/api/v1/journeys/{journey['journey_id']}/chat/voice",
            files={"file": ("clip.wav", b"fake-audio-bytes", "audio/wav")},
            headers=session_headers,
        )
        assert resp.status_code == 404

    async def test_voice_empty_audio_returns_400(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        _enable_sarvam_voice(monkeypatch)

        resp = await client.post(
            f"/api/v1/journeys/{journey['journey_id']}/chat/voice",
            files={"file": ("clip.wav", b"", "audio/wav")},
            headers=session_headers,
        )
        assert resp.status_code == 400

    async def test_voice_transcription_timeout_returns_504(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        _enable_sarvam_voice(monkeypatch)

        with patch.object(
            SarvamProvider, "transcribe", new=AsyncMock(side_effect=SarvamTimeoutError("timeout"))
        ):
            resp = await client.post(
                f"/api/v1/journeys/{journey['journey_id']}/chat/voice",
                files={"file": ("clip.wav", b"fake-audio-bytes", "audio/wav")},
                headers=session_headers,
            )
        assert resp.status_code == 504

    async def test_voice_success_returns_transcript_and_grounded_reply(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        _enable_sarvam_voice(monkeypatch)

        with patch.object(
            SarvamProvider,
            "transcribe",
            new=AsyncMock(
                return_value={"transcript": "What do I need to do next?", "language_code": "en-IN"}
            ),
        ):
            resp = await client.post(
                f"/api/v1/journeys/{journey['journey_id']}/chat/voice",
                files={"file": ("clip.wav", b"fake-audio-bytes", "audio/wav")},
                headers=session_headers,
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["transcript"] == "What do I need to do next?"
        assert body["language_code"] == "en-IN"
        assert body["reply"]

    async def test_voice_cannot_bypass_business_rules(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        """A spoken 'approve my loan' must get the same grounded, advisory
        reply a typed message would - never a fabricated approval."""
        journey = await _create_lending_journey(client, session_headers)
        _enable_sarvam_voice(monkeypatch)

        with patch.object(
            SarvamProvider,
            "transcribe",
            new=AsyncMock(
                return_value={"transcript": "Please approve my loan now.", "language_code": "en-IN"}
            ),
        ):
            resp = await client.post(
                f"/api/v1/journeys/{journey['journey_id']}/chat/voice",
                files={"file": ("clip.wav", b"fake-audio-bytes", "audio/wav")},
                headers=session_headers,
            )
        assert resp.status_code == 200, resp.text
        reply = resp.json()["reply"].lower()
        for banned in ("approved", "guaranteed"):
            assert banned not in reply

        # The journey's own readiness must be completely unaffected by voice input.
        status_resp = await client.get(
            f"/api/v1/journeys/{journey['journey_id']}", headers=session_headers
        )
        assert status_resp.status_code == 200
        assert status_resp.json()["readiness"] == journey["readiness"]
