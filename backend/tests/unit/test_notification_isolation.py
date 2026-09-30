from app.config import settings


def test_tests_never_see_real_external_integrations() -> None:
    """Guards tests/conftest.py: whatever the developer .env says, a test that
    does not opt in has n8n and Sarvam disabled with nothing to send to."""
    assert settings.N8N_ENABLED is False
    assert settings.N8N_WEBHOOK_URL == ""
    assert settings.N8N_WEBHOOK_SECRET == ""
    assert settings.SARVAM_ENABLED is False
    assert settings.SARVAM_API_KEY == ""
