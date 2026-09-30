import pytest

from app.config import Settings

SHA = "10cd574917013333c790105abdf117ba914ffff3"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, "dev"),
        ({"RENDER_GIT_COMMIT": SHA}, SHA),
        ({"GIT_SHA": "abc1234", "RENDER_GIT_COMMIT": SHA}, "abc1234"),
        ({"RENDER_GIT_COMMIT": SHA.upper()}, SHA),
        ({"GIT_SHA": "<script>alert(1)</script>"}, "dev"),
        ({"GIT_SHA": "not-a-sha"}, "dev"),
        ({"GIT_SHA": "abc"}, "dev"),
    ],
)
def test_git_sha_comes_from_deploy_metadata_and_is_only_ever_a_hash(
    monkeypatch: pytest.MonkeyPatch, env: dict, expected: str
) -> None:
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert Settings(_env_file=None).GIT_SHA == expected
