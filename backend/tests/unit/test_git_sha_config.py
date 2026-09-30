import pytest

from app.config import Settings

SHA = "10cd574917013333c790105abdf117ba914ffff3"


@pytest.mark.parametrize(
    ("app_env", "env", "expected"),
    [
        # Development: no metadata is honestly "dev".
        ("local", {}, "dev"),
        ("ci", {}, "dev"),
        ("local", {"GIT_SHA": "abc1234"}, "abc1234"),
        # Production: the platform commit is used; explicit GIT_SHA wins.
        ("production", {"RENDER_GIT_COMMIT": SHA}, SHA),
        ("production", {"GIT_SHA": "abc1234", "RENDER_GIT_COMMIT": SHA}, "abc1234"),
        ("production", {"RENDER_GIT_COMMIT": SHA.upper()}, SHA),
        # Production with missing or unusable metadata: never claims "dev".
        ("production", {}, "unknown"),
        ("production", {"RENDER_GIT_COMMIT": ""}, "unknown"),
        ("production", {"GIT_SHA": "dev"}, "unknown"),
        ("production", {"GIT_SHA": "<script>alert(1)</script>"}, "unknown"),
        ("production", {"GIT_SHA": "/opt/render/project/src"}, "unknown"),
        ("local", {"GIT_SHA": "not-a-sha"}, "dev"),
        ("local", {"GIT_SHA": "abc"}, "dev"),
    ],
)
def test_git_sha_comes_from_deploy_metadata_and_is_only_ever_a_hash(
    monkeypatch: pytest.MonkeyPatch, app_env: str, env: dict, expected: str
) -> None:
    for key in ("GIT_SHA", "RENDER_GIT_COMMIT", "APP_ENV", "SESSION_SECRET", "DEMO_RESET_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APP_ENV", app_env)
    # Non-placeholder secrets so the production startup guard lets Settings build.
    monkeypatch.setenv("SESSION_SECRET", "test-only-session-secret-0123456789abcdef")
    monkeypatch.setenv("DEMO_RESET_SECRET", "test-only-demo-reset-secret-0123456789")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert Settings(_env_file=None).GIT_SHA == expected
