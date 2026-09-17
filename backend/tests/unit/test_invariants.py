"""Phase B28 — Invariant + Safety Suite.

Tests named exactly per build plan §8 / §10:
  test_ai_cannot_write_state
  test_snapshot_update_raises
  test_snapshot_chain_never_forks
  test_rejected_action_creates_no_snapshot
  test_audit_replay_reconstructs_state  (parametrised × 6 packs)
  test_no_readiness_score_in_any_response
  test_simulate_purity_100_identical_runs
  test_planner_determinism_100_identical_paths
  test_deterministic_check_rejection_paths
  test_snapshot_creation_requires_checktoken
  test_no_prohibited_words_in_readiness_enum
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.audit import AuditWriter, replay_journey
from app.core import (
    CoreFieldState,
    CoreFieldStatus,
    CoreReadiness,
    CoreSnapshot,
    DeterministicCheckError,
    deterministic_check,
    plan,
    simulate,
)
from app.db.models import Base, JourneySnapshotModel
from app.db.repositories import AuditRepository, SessionRepository
from app.db.repositories.snapshots import SnapshotRepository
from app.db.session import create_immutability_triggers
from app.packs.contract import JourneyPackManifest
from app.packs.registry import pack_registry
from app.schemas.enums import JourneyType

# ─── shared fixture ──────────────────────────────────────────────────────────


@pytest.fixture
async def mem_db() -> AsyncSession:
    """In-memory SQLite DB with immutability triggers applied."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_immutability_triggers(conn)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    await engine.dispose()


def _blank_snapshot(
    manifest: JourneyPackManifest,
    jtype: JourneyType,
    goal: dict[str, Any] | None = None,
) -> CoreSnapshot:
    """Snapshot with every field at its default status (mostly BLOCKED)."""
    return CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=uuid4(),
        journey_type=jtype.value,
        version_number=1,
        readiness=CoreReadiness.NOT_READY,
        goal=goal or {},
        fields={
            f.key: CoreFieldState(
                key=f.key,
                label=f.label,
                status=CoreFieldStatus(f.default_status.value),
                mandatory=f.mandatory,
                derived=f.derived,
            )
            for f in manifest.state_schema
        },
    )


# ─── INVARIANT 1: app/core must not import AI, DB, or API ────────────────────


def test_ai_cannot_write_state():
    """app/core/* must never import app.ai, app.db, or app.api."""
    import app.core as core_pkg

    forbidden_prefixes = ("app.ai", "app.db", "app.api")
    violations: list[str] = []

    for _finder, module_name, _ispkg in pkgutil.walk_packages(
        core_pkg.__path__, prefix="app.core."
    ):
        mod = importlib.import_module(module_name)
        try:
            source = inspect.getsource(mod)
        except (OSError, TypeError):
            continue

        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for forbidden in forbidden_prefixes:
                if f"import {forbidden}" in stripped or f"from {forbidden}" in stripped:
                    violations.append(f"{module_name}: imports {forbidden!r}")
                    break

    assert not violations, "app/core must be pure (no AI, DB, or API imports):\n" + "\n".join(
        violations
    )


# ─── INVARIANT 2: snapshot UPDATE raises via DB trigger ──────────────────────


@pytest.mark.asyncio
async def test_snapshot_update_raises(mem_db: AsyncSession):
    """DB trigger must reject any attempt to UPDATE a journey_snapshots row."""
    snap_id = uuid4()
    snap = JourneySnapshotModel(
        id=snap_id,
        journey_id=uuid4(),
        version_number=1,
        previous_snapshot_id=None,
        readiness="NOT_READY",
        fields={},
        goal={},
        created_at=datetime.now(UTC),
    )
    mem_db.add(snap)
    await mem_db.flush()
    await mem_db.commit()

    # Re-fetch via ORM then mutate — this routes through the SQLAlchemy UPDATE path
    # which the BEFORE UPDATE trigger intercepts via RAISE(ABORT, 'immutable...')
    with pytest.raises(Exception) as exc_info:
        snap_row = await mem_db.get(JourneySnapshotModel, snap_id)
        assert snap_row is not None
        snap_row.readiness = "READY"  # type: ignore[assignment]
        await mem_db.commit()

    assert "immutable" in str(exc_info.value).lower(), (
        f"Expected 'immutable' in trigger error, got: {exc_info.value}"
    )


# ─── INVARIANT 3: snapshot chain never forks ─────────────────────────────────


@pytest.mark.asyncio
async def test_snapshot_chain_never_forks(mem_db: AsyncSession):
    """Unique constraint on (journey_id, previous_snapshot_id) prevents chain forking."""
    journey_id = uuid4()
    snap1_id = uuid4()
    snap2a_id = uuid4()
    snap2b_id = uuid4()

    snap1 = JourneySnapshotModel(
        id=snap1_id,
        journey_id=journey_id,
        version_number=1,
        previous_snapshot_id=None,
        readiness="NOT_READY",
        fields={},
        goal={},
        created_at=datetime.now(UTC),
    )
    mem_db.add(snap1)
    await mem_db.flush()

    snap2a = JourneySnapshotModel(
        id=snap2a_id,
        journey_id=journey_id,
        version_number=2,
        previous_snapshot_id=snap1_id,
        readiness="NOT_READY",
        fields={},
        goal={},
        created_at=datetime.now(UTC),
    )
    mem_db.add(snap2a)
    await mem_db.flush()

    # Second child from the same parent — fork attempt
    snap2b = JourneySnapshotModel(
        id=snap2b_id,
        journey_id=journey_id,
        version_number=3,
        previous_snapshot_id=snap1_id,  # same previous_snapshot_id → fork
        readiness="NOT_READY",
        fields={},
        goal={},
        created_at=datetime.now(UTC),
    )
    mem_db.add(snap2b)

    with pytest.raises(SQLAlchemyError):  # IntegrityError or OperationalError
        await mem_db.flush()


# ─── INVARIANT 4: rejected action creates no snapshot ────────────────────────


@pytest.mark.asyncio
async def test_rejected_action_creates_no_snapshot(mem_db: AsyncSession):
    """deterministic_check is a pure function; a rejection must not touch the DB."""
    pack_registry.load_all()
    manifest = pack_registry.get_pack(JourneyType.LENDING)
    assert manifest is not None

    snap_repo = SnapshotRepository(mem_db)
    journey_id = uuid4()
    initial_snap_id = uuid4()

    initial = JourneySnapshotModel(
        id=initial_snap_id,
        journey_id=journey_id,
        version_number=1,
        previous_snapshot_id=None,
        readiness="NOT_READY",
        fields={},
        goal={},
        created_at=datetime.now(UTC),
    )
    mem_db.add(initial)
    await mem_db.flush()
    await mem_db.commit()

    snap = _blank_snapshot(manifest, JourneyType.LENDING)

    before = await snap_repo.list_by_journey_id(journey_id)
    assert len(before) == 1

    # Stale snapshot → DeterministicCheckError (ACTION_STALE)
    with pytest.raises(DeterministicCheckError) as exc_info:
        deterministic_check(
            snapshot=snap,
            expected_snapshot_id=uuid4(),  # intentionally wrong
            action_id=manifest.actions[0].action_id,
            action_input=None,
            manifest=manifest,
        )
    assert exc_info.value.code.value == "ACTION_STALE"

    after = await snap_repo.list_by_journey_id(journey_id)
    assert len(after) == 1, (
        f"Rejected action must not create snapshots; found {len(after)} after rejection"
    )


# ─── INVARIANT 5: audit replay reconstructs state × 6 packs ─────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("jtype", list(JourneyType))
async def test_audit_replay_reconstructs_state(jtype: JourneyType, mem_db: AsyncSession):
    """Replaying audit events reconstructs the correct final snapshot for each pack."""
    pack_registry.load_all()
    manifest = pack_registry.get_pack(jtype)
    assert manifest is not None, f"Pack not found for {jtype}"

    session_repo = SessionRepository(mem_db)
    audit_repo = AuditRepository(mem_db)
    writer = AuditWriter(audit_repo)

    sess = await session_repo.create(expires_at=datetime.now(UTC) + timedelta(days=1))
    journey_id = uuid4()
    snap1_id = uuid4()
    snap2_id = uuid4()

    defaults = manifest.simulation_defaults or {}
    initial_values: dict[str, Any] = {
        f.key: defaults.get(f.key, True) for f in manifest.state_schema if not f.derived
    }

    await writer.record_journey_created(
        journey_id=journey_id,
        session_id=sess.id,
        journey_type=jtype.value,
        goal={"amount": 100000},
        initial_snapshot_id=snap1_id,
        initial_values=initial_values,
    )

    first_action = next(
        (a for a in manifest.actions),
        None,
    )
    assert first_action is not None

    new_values = {s: defaults.get(s, True) for s in first_action.satisfies}
    await writer.record_action_executed(
        journey_id=journey_id,
        session_id=sess.id,
        action_id=first_action.action_id,
        token_id=uuid4(),
        snapshot_id=snap2_id,
        version_number=2,
        action_input=new_values,
        new_values=new_values,
    )

    events = await audit_repo.list_by_journey_id(journey_id)
    assert len(events) == 2, f"Expected 2 audit events for {jtype}, got {len(events)}"

    replayed = replay_journey(journey_id=journey_id, events=events, manifest=manifest)

    assert replayed.journey_id == journey_id, f"Journey ID mismatch for {jtype}"
    assert replayed.snapshot_id == snap2_id, f"Snapshot ID mismatch for {jtype}"
    assert replayed.version_number == 2, f"Version mismatch for {jtype}"

    for key in new_values:
        if key in replayed.fields:
            assert replayed.fields[key].status == CoreFieldStatus.SATISFIED, (
                f"Field '{key}' must be SATISFIED after replay for {jtype}"
            )


# ─── INVARIANT 6: no numeric score in any response schema ────────────────────


def test_no_readiness_score_in_any_response():
    """No API response schema may contain a numeric readiness/score field."""
    import app.schemas as schemas_pkg

    score_pattern = re.compile(
        r"(readiness_score|eligibility_score|credit_score|probability|approved|approval)",
        re.IGNORECASE,
    )

    violations: list[str] = []
    for _finder, module_name, _ispkg in pkgutil.walk_packages(
        schemas_pkg.__path__, prefix="app.schemas."
    ):
        mod = importlib.import_module(module_name)
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if not hasattr(obj, "model_fields"):
                continue
            for field_name in obj.model_fields:
                if score_pattern.search(field_name):
                    violations.append(f"{module_name}.{name}.{field_name}")

    assert not violations, (
        "Response schemas must not expose numeric score/approval fields:\n" + "\n".join(violations)
    )


def test_no_prohibited_words_in_readiness_enum():
    """The Readiness enum must not contain approved/score/probability."""
    from app.schemas.enums import Readiness

    banned = {"approved", "approval", "probability", "score", "eligible", "guaranteed"}
    for member in Readiness:
        for word in banned:
            assert word not in member.value.lower(), (
                f"Readiness enum '{member.value}' contains prohibited word '{word}'"
            )


# ─── PURITY: simulate returns identical output × 100 runs ────────────────────


@pytest.mark.parametrize("jtype", list(JourneyType))
def test_simulate_purity_100_identical_runs(jtype: JourneyType):
    """simulate() is a pure function: 100 identical inputs → 100 identical outputs."""
    pack_registry.load_all()
    manifest = pack_registry.get_pack(jtype)
    assert manifest is not None

    snap = _blank_snapshot(manifest, jtype)
    defaults = manifest.simulation_defaults or {}

    # Pick first action with no preconditions, fall back to first action
    first_action = next(
        (a for a in manifest.actions if not a.preconditions),
        manifest.actions[0],
    )
    action_input = {s: defaults.get(s, True) for s in first_action.satisfies}

    results = [simulate(first_action.action_id, action_input, snap, manifest) for _ in range(100)]

    first = results[0]
    for i, r in enumerate(results[1:], start=1):
        assert r.predicted_readiness == first.predicted_readiness, (
            f"simulate() impure: run {i} differs in readiness for {jtype}"
        )
        assert {f.key for f in r.newly_satisfied} == {f.key for f in first.newly_satisfied}, (
            f"simulate() impure: newly_satisfied differs on run {i} for {jtype}"
        )
        assert r.progress_after.completed == first.progress_after.completed, (
            f"simulate() impure: progress differs on run {i} for {jtype}"
        )


# ─── DETERMINISM: planner returns identical path × 100 runs ──────────────────


@pytest.mark.parametrize("jtype", list(JourneyType))
def test_planner_determinism_100_identical_paths(jtype: JourneyType):
    """plan() is deterministic: 100 identical inputs → 100 identical orderings."""
    pack_registry.load_all()
    manifest = pack_registry.get_pack(jtype)
    assert manifest is not None

    snap = _blank_snapshot(manifest, jtype)
    results = [plan(snap, manifest) for _ in range(100)]

    first_ids = [a.action_id for a in results[0].actions]
    for i, r in enumerate(results[1:], start=1):
        run_ids = [a.action_id for a in r.actions]
        assert run_ids == first_ids, (
            f"plan() not deterministic: run {i} returned {run_ids} vs {first_ids} for {jtype}"
        )


# ─── REJECTION PATHS: deterministic_check raises the right error code ────────


@pytest.mark.parametrize(
    "label,failure_mode,expected_code",
    [
        ("stale_snapshot", "stale", "ACTION_STALE"),
        ("unknown_action", "unknown_action", "ACTION_INVALID"),
    ],
)
def test_deterministic_check_rejection_paths(label: str, failure_mode: str, expected_code: str):
    """deterministic_check raises the correct ErrorCode for each rejection path."""
    pack_registry.load_all()
    manifest = pack_registry.get_pack(JourneyType.LENDING)
    assert manifest is not None

    snap = _blank_snapshot(manifest, JourneyType.LENDING)
    first_action = manifest.actions[0]

    if failure_mode == "stale":
        with pytest.raises(DeterministicCheckError) as exc_info:
            deterministic_check(
                snapshot=snap,
                expected_snapshot_id=uuid4(),  # wrong id
                action_id=first_action.action_id,
                action_input=None,
                manifest=manifest,
            )
        assert exc_info.value.code.value == expected_code

    elif failure_mode == "unknown_action":
        with pytest.raises(DeterministicCheckError) as exc_info:
            deterministic_check(
                snapshot=snap,
                expected_snapshot_id=snap.snapshot_id,
                action_id="NONEXISTENT_ACTION_ID_ZZZZZ",
                action_input=None,
                manifest=manifest,
            )
        assert exc_info.value.code.value == expected_code


# ─── CHECKTOKEN GATE: SnapshotRepository.create() requires CheckToken ────────


@pytest.mark.asyncio
async def test_snapshot_creation_requires_checktoken(mem_db: AsyncSession):
    """SnapshotRepository.create() must refuse any non-CheckToken token argument."""
    snap_repo = SnapshotRepository(mem_db)

    with pytest.raises(TypeError, match="CheckToken"):
        await snap_repo.create(
            token="not-a-checktoken",  # type: ignore[arg-type]
            readiness="READY",
            fields={},
        )
