import pytest

from app.config import settings
from app.security.reviewer import reviewer_access_code_problem


@pytest.mark.parametrize(
    ("env", "code", "expect"),
    [
        ("local", "", None),
        ("ci", "x", None),
        ("demo", "", "unset"),
        ("demo", "short", "weak"),
        ("demo", "aaaaaaaaaaaaaaaaaaaa", "weak"),
        ("demo", "k3J9-qLm2-Zx7P-w8Rt", None),
    ],
)
def test_reviewer_access_code_problem(
    monkeypatch: pytest.MonkeyPatch, env: str, code: str, expect: str | None
) -> None:
    monkeypatch.setattr(settings, "APP_ENV", env)
    monkeypatch.setattr(settings, "REVIEWER_ACCESS_CODE", code)
    problem = reviewer_access_code_problem()
    if expect is None:
        assert problem is None
    else:
        assert problem is not None and problem.startswith(expect)
        assert code == "" or code not in problem
