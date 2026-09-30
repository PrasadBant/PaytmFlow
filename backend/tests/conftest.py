import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _no_real_external_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer .env may enable n8n (real production webhook) or Sarvam
    (cloud AI); tests must never reach either. Both start disabled with no URL,
    secret or key, so a test that opts in must also supply its own dummy
    endpoint and mock the network - forgetting to is a no-op, not a real call."""
    monkeypatch.setattr(settings, "N8N_ENABLED", False)
    monkeypatch.setattr(settings, "N8N_WEBHOOK_URL", "")
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "SARVAM_ENABLED", False)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "")
