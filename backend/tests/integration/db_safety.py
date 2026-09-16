"""Integration-test database safety boundary.

The integration suite's `db_engine` fixture (conftest.py) runs genuinely
destructive setup/teardown - `Base.metadata.drop_all` then `create_all`, at
BOTH session start AND session end - against whatever PostgreSQL URL it
resolves. That is correct and intended for a disposable, ephemeral test
database (exactly what CI provisions). It is catastrophic against the SAME
long-lived PostgreSQL instance a developer also runs the live demo app
(`make api`) against: a plain `pytest tests/integration` run pointed at that
instance silently wipes every real journey/session/evidence row out from
under it - a real incident this project's own QA hit twice (see
backend/docs/paytmflow_final_end_to_end_release_report.md, BUG-009's
investigation trail: `relation "sessions" does not exist` on the live app
immediately after an integration-test run).

This module is the ONLY place that decides which URL destructive test setup
is allowed to touch. `conftest.py` calls it immediately before its first
`drop_all`/`create_all` and nowhere else - it is deliberately not wired into
`app.config.Settings` or any non-test code path, since the demo app itself
must never be affected by this module existing at all.

Every function here is pure (no I/O, no network) so the guard logic itself
is fully, fast, and deterministically unit-testable without a real
PostgreSQL instance - see test_db_safety_guard.py.
"""

from __future__ import annotations

import os

from sqlalchemy.engine import make_url

# The exact, literal default `DATABASE_URL` shipped by app/config.py and
# backend/docker-compose.yml - the real database a local demo/dev `make api`
# run (and this project's own live QA sessions) actually writes real,
# persisted journeys/evidence/sessions into. Compared byte-for-byte (after
# scheme normalization) as a hard, unconditional reject - there is no
# legitimate reason an integration test run would ever intentionally target
# this exact URL destructively, so unlike the naming-convention check below,
# this one has no override.
KNOWN_DEMO_DATABASE_URL = "postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow"

# Escape hatch for the one legitimate exception the naming-convention check
# (below) cannot anticipate: a CI-provisioned PostgreSQL whose database
# happens to not have "test" in its name but is genuinely a fresh,
# disposable, no-real-data instance. Never bypasses the exact
# known-demo-URL reject above - that one is never overridable.
ALLOW_UNCONVENTIONAL_NAME_ENV_VAR = "PAYTMFLOW_ALLOW_DESTRUCTIVE_TEST_DB"

# Explicit opt-in for "use exactly this URL as the test database" - setting
# this IS the required explicit test-environment marker: a developer or CI
# job that sets it has made a deliberate, affirmative choice about which
# database destructive test setup may touch, rather than the fixture
# silently reusing whatever DATABASE_URL happens to be configured for the
# live app.
TEST_DATABASE_URL_ENV_VAR = "TEST_DATABASE_URL"


class UnsafeTestDatabaseError(RuntimeError):
    """Raised instead of ever running destructive setup against a database
    that was not proven safe. Fail closed, never a silent guess."""


def _normalize_scheme(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def derive_test_database_url(source_url: str) -> str:
    """Given any PostgreSQL URL (typically `settings.DATABASE_URL`, the live
    demo app's own connection string), returns a URL pointing at a SEPARATE,
    dedicated database on the same server: the same name with `_test`
    appended, unless the name already looks like a test database. This is
    what makes "a dedicated test database by default" require zero extra
    configuration in the common case - no new container, no manual
    `createdb` step (conftest.py auto-creates it if missing) - while
    guaranteeing PostgreSQL itself, not just a naming convention, keeps it
    fully isolated from whatever the demo database holds: DROP/CREATE
    against one database can never touch a different one."""
    url = _normalize_scheme(source_url)
    parsed = make_url(url)
    db_name = parsed.database or ""
    if "test" in db_name.lower():
        return url
    # `URL.__str__`/`str(...)` redacts the password as "***" (a SQLAlchemy
    # safety default for printing/logging) - `render_as_string` with
    # `hide_password=False` is required here since this return value is
    # actually used to open a real connection, not just displayed.
    return parsed.set(database=f"{db_name}_test").render_as_string(hide_password=False)


def resolve_test_database_url(fallback_url: str) -> str:
    """The single entrypoint conftest.py calls to decide which URL to
    connect the integration suite to. `TEST_DATABASE_URL`, if set, is used
    verbatim - the explicit test-environment marker for a genuinely
    separate dedicated test container/instance. Otherwise a dedicated
    database is derived from `fallback_url` (typically
    `settings.DATABASE_URL`) automatically, requiring no configuration."""
    explicit = os.environ.get(TEST_DATABASE_URL_ENV_VAR)
    if explicit:
        return _normalize_scheme(explicit)
    return derive_test_database_url(fallback_url)


def assert_safe_for_destructive_db_setup(url: str) -> None:
    """The fail-closed gate. Must be called immediately before the FIRST
    destructive statement (`drop_all`/`create_all`) against a real
    PostgreSQL connection - never after, never skipped. Raises
    `UnsafeTestDatabaseError` (never returns a "maybe") unless `url` is
    provably safe to destroy."""
    normalized = _normalize_scheme(url)

    if normalized == KNOWN_DEMO_DATABASE_URL:
        raise UnsafeTestDatabaseError(
            "Refusing to run destructive integration-test database setup "
            f"against {normalized!r} - this is the exact, literal default "
            "DATABASE_URL for the real PaytmFlow demo/dev database "
            "(app/config.py, backend/docker-compose.yml). Running the "
            "integration suite against it would DROP every real table. Set "
            f"{TEST_DATABASE_URL_ENV_VAR} to a dedicated test database "
            "instead - there is no override for this specific URL."
        )

    parsed = make_url(normalized)
    db_name = (parsed.database or "").lower()
    if "test" not in db_name:
        if os.environ.get(ALLOW_UNCONVENTIONAL_NAME_ENV_VAR) == "1":
            return
        raise UnsafeTestDatabaseError(
            "Refusing to run destructive integration-test database setup "
            f"against database {parsed.database!r} - its name does not look "
            'like a dedicated test database (expected "test" to appear in '
            f"the name). Set {TEST_DATABASE_URL_ENV_VAR} to a URL whose "
            'database name contains "test", or - only if this really is a '
            "fresh, disposable, no-real-data instance (e.g. a "
            f"CI-provisioned container) - set "
            f"{ALLOW_UNCONVENTIONAL_NAME_ENV_VAR}=1 to confirm that "
            "explicitly."
        )
