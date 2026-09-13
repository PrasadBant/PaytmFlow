import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base
from app.db.session import create_immutability_triggers, get_db
from app.eval.runner import Scenario, load_all_scenarios, run_scenario
from app.main import app
from app.packs.registry import pack_registry

# Load all 36 YAML scenarios
_SCENARIOS = load_all_scenarios()
_SCENARIO_IDS = [f"{s.pack}__{s.family}" for s in _SCENARIOS]


@pytest.fixture(autouse=True)
def load_manifests():
    pack_registry.load_all()


@pytest.fixture
async def app_context():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_immutability_triggers(conn)

    session_maker = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, session_maker

    app.dependency_overrides.clear()
    await test_engine.dispose()


def test_scenario_suite_completeness():
    """Verify that all 36 scenarios (6 packs x 6 families) are present."""
    assert len(_SCENARIOS) == 36
    packs = {"LENDING", "INSURANCE", "CREDIT_CARD", "KYC", "ACCOUNT_OPENING", "INVESTMENT"}
    families = {
        "GOLDEN",
        "MULTI_BLOCKER",
        "AMBIGUITY_CONFLICT",
        "ALTERNATE_OR_OVERRIDE",
        "INVALID_ACTION",
        "STALE_ACTION",
    }
    found_pairs = {(s.pack, s.family) for s in _SCENARIOS}
    expected_pairs = {(p, f) for p in packs for f in families}
    assert found_pairs == expected_pairs


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", _SCENARIOS, ids=_SCENARIO_IDS)
async def test_scenario_execution(
    scenario: Scenario,
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    """Execute each of the 36 scenarios against the real FastAPI app and DB engine."""
    client, session_maker = app_context
    result = await run_scenario(scenario, client, session_maker)
    assert result.passed is True, f"Scenario {scenario.id} failed: {result.error_message}"
    assert result.steps_executed == result.total_steps
