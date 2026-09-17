"""Regression tests for the integration-test database safety boundary
(db_safety.py). Pure logic - no real PostgreSQL needed, deliberately fast,
so this guard is always exercised regardless of whether Postgres is
reachable in the current environment.

Context (final-release-freeze hardening phase): this project's own QA hit a
real incident twice in the same session where running `pytest
tests/integration` against the live demo `DATABASE_URL` silently dropped
every real table (`relation "sessions" does not exist` on the running demo
app immediately after). These tests prove the guard that now prevents that
class of incident structurally, not just "don't do that again"."""

import os

import pytest
from db_safety import (
    ALLOW_UNCONVENTIONAL_NAME_ENV_VAR,
    KNOWN_DEMO_DATABASE_URL,
    TEST_DATABASE_URL_ENV_VAR,
    UnsafeTestDatabaseError,
    assert_safe_for_destructive_db_setup,
    derive_test_database_url,
    resolve_test_database_url,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    """Every test in this file controls its own environment explicitly -
    never inherits whatever TEST_DATABASE_URL/override the outer test run
    (or a developer's shell) happens to have set."""
    monkeypatch.delenv(TEST_DATABASE_URL_ENV_VAR, raising=False)
    monkeypatch.delenv(ALLOW_UNCONVENTIONAL_NAME_ENV_VAR, raising=False)


class TestDeriveTestDatabaseUrl:
    def test_appends_test_suffix_to_a_normal_database_name(self):
        derived = derive_test_database_url(
            "postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow"
        )
        assert derived == "postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow_test"

    def test_is_idempotent_when_the_name_already_looks_like_a_test_database(self):
        derived = derive_test_database_url(
            "postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow_test"
        )
        assert derived == "postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow_test"

    def test_normalizes_the_bare_postgresql_scheme(self):
        derived = derive_test_database_url(
            "postgresql://paytmflow:paytmflow@localhost:5432/paytmflow"
        )
        assert derived.startswith("postgresql+psycopg://")
        assert derived.endswith("/paytmflow_test")

    def test_preserves_a_nonstandard_host_and_port(self):
        # Exactly this project's own live QA setup this session: the demo
        # container mapped to a non-default host port.
        derived = derive_test_database_url(
            "postgresql+psycopg://paytmflow:paytmflow@127.0.0.1:5433/paytmflow"
        )
        assert derived == "postgresql+psycopg://paytmflow:paytmflow@127.0.0.1:5433/paytmflow_test"


class TestResolveTestDatabaseUrl:
    def test_prefers_an_explicit_test_database_url_env_var(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(
            TEST_DATABASE_URL_ENV_VAR,
            "postgresql+psycopg://ci:ci@ci-postgres:5432/paytmflow_ci_test",
        )
        resolved = resolve_test_database_url(
            "postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow"
        )
        assert resolved == "postgresql+psycopg://ci:ci@ci-postgres:5432/paytmflow_ci_test"

    def test_derives_from_the_fallback_when_no_explicit_marker_is_set(self):
        resolved = resolve_test_database_url(
            "postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow"
        )
        assert resolved == "postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow_test"


class TestAssertSafeForDestructiveDbSetup:
    def test_rejects_the_exact_known_demo_database_url(self):
        with pytest.raises(UnsafeTestDatabaseError, match="real PaytmFlow demo/dev database"):
            assert_safe_for_destructive_db_setup(KNOWN_DEMO_DATABASE_URL)

    def test_rejects_the_known_demo_url_even_with_the_bare_postgresql_scheme(self):
        with pytest.raises(UnsafeTestDatabaseError):
            assert_safe_for_destructive_db_setup(
                "postgresql://paytmflow:paytmflow@localhost:5432/paytmflow"
            )

    def test_the_unconventional_name_override_does_not_bypass_the_known_demo_url_reject(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        # Real safety-critical regression: the escape hatch exists ONLY for
        # a non-"test"-named database that is otherwise NOT the literal
        # known demo URL. It must never rescue the one URL that always
        # means "this is the real, persistent demo data".
        monkeypatch.setenv(ALLOW_UNCONVENTIONAL_NAME_ENV_VAR, "1")
        with pytest.raises(UnsafeTestDatabaseError):
            assert_safe_for_destructive_db_setup(KNOWN_DEMO_DATABASE_URL)

    def test_rejects_a_database_whose_name_does_not_look_like_a_test_database(self):
        with pytest.raises(
            UnsafeTestDatabaseError, match="does not look like a dedicated test database"
        ):
            assert_safe_for_destructive_db_setup(
                "postgresql+psycopg://paytmflow:paytmflow@127.0.0.1:5433/paytmflow"
            )

    def test_allows_a_database_whose_name_contains_test(self):
        # Must not raise.
        assert_safe_for_destructive_db_setup(
            "postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow_test"
        )

    def test_allows_a_nonconventional_name_when_the_explicit_override_is_set(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv(ALLOW_UNCONVENTIONAL_NAME_ENV_VAR, "1")
        # Must not raise - a genuinely CI-provisioned, non-"test"-named,
        # disposable database, explicitly confirmed by a human/CI config.
        assert_safe_for_destructive_db_setup(
            "postgresql+psycopg://ci:ci@ci-postgres:5432/paytmflow_ephemeral"
        )

    def test_the_override_env_var_requires_the_exact_value_one(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        # A stray truthy-looking value ("true", "yes") must NOT silently
        # grant the override - only the exact documented "1".
        monkeypatch.setenv(ALLOW_UNCONVENTIONAL_NAME_ENV_VAR, "true")
        with pytest.raises(UnsafeTestDatabaseError):
            assert_safe_for_destructive_db_setup(
                "postgresql+psycopg://paytmflow:paytmflow@127.0.0.1:5433/paytmflow"
            )


class TestFullResolutionEndToEnd:
    """Proves the whole chain conftest.py actually uses: resolve, then
    assert-safe, exactly as `db_engine` calls them in sequence."""

    def test_default_local_demo_url_resolves_to_a_safe_derived_test_url(self):
        resolved = resolve_test_database_url(
            "postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow"
        )
        # Must not raise - this is the exact zero-configuration path a
        # fresh checkout takes.
        assert_safe_for_destructive_db_setup(resolved)
        assert resolved != KNOWN_DEMO_DATABASE_URL

    def test_an_explicit_but_unsafe_test_database_url_is_still_caught(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        # Defense in depth: even if a developer accidentally sets
        # TEST_DATABASE_URL to the literal demo URL, the fixture must still
        # refuse rather than trust the env var blindly.
        monkeypatch.setenv(TEST_DATABASE_URL_ENV_VAR, KNOWN_DEMO_DATABASE_URL)
        resolved = resolve_test_database_url(
            "postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow"
        )
        with pytest.raises(UnsafeTestDatabaseError):
            assert_safe_for_destructive_db_setup(resolved)

    def test_env_var_names_match_what_this_modules_docstring_and_conftest_advertise(self):
        # Cheap guard against the constants silently drifting from the
        # error messages / docs that reference them by name.
        assert TEST_DATABASE_URL_ENV_VAR == "TEST_DATABASE_URL"
        assert ALLOW_UNCONVENTIONAL_NAME_ENV_VAR == "PAYTMFLOW_ALLOW_DESTRUCTIVE_TEST_DB"
        assert os.environ.get(TEST_DATABASE_URL_ENV_VAR) is None
