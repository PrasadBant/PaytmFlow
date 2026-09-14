"""Startup-guard regression tests (final-hardening phase, Part 3A):
`Settings` must refuse to construct when a security-critical secret is
still its known placeholder default AND `APP_ENV` is outside the
explicitly-allowed `local`/`ci` set - while remaining fully usable in
`local`, `ci`, and a properly-configured `demo` (or any other) environment.

Constructs `Settings` directly (not the module-level `app.config.settings`
singleton, which is already built once at import time from this
environment's real env vars/.env) so each case gets a fresh, isolated
instantiation.
"""

import pytest

from app.config import Settings


def _base_kwargs(**overrides) -> dict:
    # Only the fields relevant to the guard are varied; everything else
    # keeps its normal default.
    kwargs = {"APP_ENV": "local"}
    kwargs.update(overrides)
    return kwargs


def test_local_env_allows_placeholder_secrets():
    s = Settings(**_base_kwargs(APP_ENV="local"))
    assert s.SESSION_SECRET == "change-me-32-bytes-minimum-session-secret-key"


def test_ci_env_allows_placeholder_secrets():
    s = Settings(**_base_kwargs(APP_ENV="ci"))
    assert s.DEMO_RESET_SECRET == "change-me-demo-reset-secret"


def test_demo_env_with_placeholder_session_secret_refuses_to_start():
    with pytest.raises(ValueError, match="SESSION_SECRET"):
        Settings(
            **_base_kwargs(
                APP_ENV="demo",
                DEMO_RESET_SECRET="a-real-unique-demo-reset-secret-value",
            )
        )


def test_demo_env_with_placeholder_demo_reset_secret_refuses_to_start():
    with pytest.raises(ValueError, match="DEMO_RESET_SECRET"):
        Settings(
            **_base_kwargs(
                APP_ENV="demo",
                SESSION_SECRET="a-real-unique-session-secret-value-32bytes",
            )
        )


def test_demo_env_with_both_placeholders_lists_both_in_one_error():
    with pytest.raises(ValueError) as exc_info:
        Settings(**_base_kwargs(APP_ENV="demo"))
    message = str(exc_info.value)
    assert "SESSION_SECRET" in message
    assert "DEMO_RESET_SECRET" in message


def test_demo_env_with_real_secrets_starts_successfully():
    s = Settings(
        **_base_kwargs(
            APP_ENV="demo",
            SESSION_SECRET="a-real-unique-session-secret-value-32bytes",
            DEMO_RESET_SECRET="a-real-unique-demo-reset-secret-value",
        )
    )
    assert s.APP_ENV == "demo"


def test_unknown_app_env_value_is_also_guarded():
    """Any APP_ENV other than the two explicitly-allowed values is treated
    as "not provably safe" - not just the literal string "demo"."""
    with pytest.raises(ValueError, match="SESSION_SECRET"):
        Settings(
            **_base_kwargs(
                APP_ENV="staging",
                DEMO_RESET_SECRET="a-real-unique-demo-reset-secret-value",
            )
        )


def test_error_message_never_contains_the_actual_secret_value():
    """The guard must name which settings are unsafe without ever
    echoing back a real-looking secret value (there is none here since
    both are still placeholders, but this also guards against a future
    change accidentally interpolating `getattr(self, name)` into the
    message)."""
    with pytest.raises(ValueError) as exc_info:
        Settings(**_base_kwargs(APP_ENV="demo"))
    message = str(exc_info.value)
    assert "change-me" not in message
