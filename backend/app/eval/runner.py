import asyncio
import os
import sys
import time
import warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.models import CheckToken
from app.db.models import Base
from app.db.repositories.journeys import JourneyRepository
from app.db.repositories.snapshots import SnapshotRepository
from app.db.session import create_immutability_triggers, get_db
from app.main import app
from app.packs.registry import pack_registry


@dataclass
class ScenarioStep:
    type: str = "action"
    action_id: str | None = None
    input: dict[str, Any] | None = None
    ambiguity_id: str | None = None
    field: str | None = None
    reason: str | None = None
    question: str | None = None
    answer_type: str | None = None
    answer: Any | None = None
    use_stale_snapshot: bool = False
    expected_status_code: int = 200
    expected_readiness: str | None = None
    expected_version: int | None = None
    expected_completed_count: int | None = None
    expected_error_code: str | None = None
    expected_recommended_action_id: list[str] | str | None = None


@dataclass
class Scenario:
    id: str
    pack: str
    family: str
    description: str
    initial_goal: dict[str, Any]
    steps: list[ScenarioStep] = field(default_factory=list)


@dataclass
class ScenarioResult:
    scenario_id: str
    pack: str
    family: str
    passed: bool
    steps_executed: int
    total_steps: int
    error_message: str | None = None
    duration_ms: float = 0.0


def load_scenario(file_path: Path | str) -> Scenario:
    path = Path(file_path)
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    scenario_id = path.stem if not data.get("id") else data["id"]
    pack = data.get("pack", "").upper()
    family = data.get("family", "").upper()
    description = data.get("description", "")
    initial_goal = data.get("initial_goal", {})

    steps = []
    for s_dict in data.get("steps", []):
        step = ScenarioStep(
            type=s_dict.get("type", "action"),
            action_id=s_dict.get("action_id"),
            input=s_dict.get("input"),
            ambiguity_id=s_dict.get("ambiguity_id"),
            field=s_dict.get("field"),
            reason=s_dict.get("reason"),
            question=s_dict.get("question"),
            answer_type=s_dict.get("answer_type"),
            answer=s_dict.get("answer"),
            use_stale_snapshot=s_dict.get("use_stale_snapshot", False),
            expected_status_code=s_dict.get("expected_status_code", 200),
            expected_readiness=s_dict.get("expected_readiness"),
            expected_version=s_dict.get("expected_version"),
            expected_completed_count=s_dict.get("expected_completed_count"),
            expected_error_code=s_dict.get("expected_error_code"),
            expected_recommended_action_id=s_dict.get("expected_recommended_action_id"),
        )
        steps.append(step)

    return Scenario(
        id=f"{pack.lower()}__{family.lower()}" if not data.get("id") else scenario_id,
        pack=pack,
        family=family,
        description=description,
        initial_goal=initial_goal,
        steps=steps,
    )


def load_all_scenarios(scenarios_dir: Path | str | None = None) -> list[Scenario]:
    if scenarios_dir is None:
        scenarios_dir = Path(__file__).parent / "scenarios"
    else:
        scenarios_dir = Path(scenarios_dir)

    scenarios = []
    for yaml_path in sorted(scenarios_dir.glob("**/*.yaml")):
        scenarios.append(load_scenario(yaml_path))
    return scenarios


async def run_scenario(
    scenario: Scenario,
    client: AsyncClient,
    session_maker: async_sessionmaker,
) -> ScenarioResult:
    start_time = time.perf_counter()
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    steps_executed = 0
    total_steps = len(scenario.steps)

    try:
        # Step 0: Create journey
        create_payload = {
            "journey_type": scenario.pack,
            "goal": scenario.initial_goal,
        }
        res = await client.post("/api/v1/journeys", json=create_payload, headers=headers)
        if res.status_code != 201:
            return ScenarioResult(
                scenario_id=scenario.id,
                pack=scenario.pack,
                family=scenario.family,
                passed=False,
                steps_executed=0,
                total_steps=total_steps,
                error_message=f"Failed to create journey: HTTP {res.status_code} - {res.text}",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        journey_data = res.json()
        journey_id = journey_data["journey_id"]
        current_snapshot_id = journey_data["snapshot_id"]
        initial_snapshot_id = current_snapshot_id

        # Execute scenario steps
        for idx, step in enumerate(scenario.steps):
            if step.type == "action":
                snap_to_send = (
                    initial_snapshot_id if step.use_stale_snapshot else current_snapshot_id
                )
                action_payload = {
                    "action_id": step.action_id,
                    "expected_snapshot_id": snap_to_send,
                    "idempotency_key": str(uuid4()),
                    "input": step.input or {},
                }
                act_res = await client.post(
                    f"/api/v1/journeys/{journey_id}/actions",
                    json=action_payload,
                    headers=headers,
                )

                if act_res.status_code != step.expected_status_code:
                    return ScenarioResult(
                        scenario_id=scenario.id,
                        pack=scenario.pack,
                        family=scenario.family,
                        passed=False,
                        steps_executed=steps_executed,
                        total_steps=total_steps,
                        error_message=(
                            f"Step {idx + 1} (action '{step.action_id}'): "
                            f"Expected {step.expected_status_code}, "
                            f"got {act_res.status_code}: {act_res.text}"
                        ),
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                    )

                if act_res.status_code == 200:
                    data = act_res.json()
                    current_snapshot_id = data["journey"]["snapshot_id"]
                    j_ver = data["journey"]["version_number"]
                    j_readiness = data["journey"]["readiness"]
                    j_completed = data["journey"]["progress"]["completed"]

                    if step.expected_version is not None and j_ver != step.expected_version:
                        return ScenarioResult(
                            scenario_id=scenario.id,
                            pack=scenario.pack,
                            family=scenario.family,
                            passed=False,
                            steps_executed=steps_executed,
                            total_steps=total_steps,
                            error_message=(
                                f"Step {idx + 1}: Expected version "
                                f"{step.expected_version}, got {j_ver}"
                            ),
                            duration_ms=(time.perf_counter() - start_time) * 1000,
                        )

                    if (
                        step.expected_readiness is not None
                        and j_readiness != step.expected_readiness
                    ):
                        return ScenarioResult(
                            scenario_id=scenario.id,
                            pack=scenario.pack,
                            family=scenario.family,
                            passed=False,
                            steps_executed=steps_executed,
                            total_steps=total_steps,
                            error_message=(
                                f"Step {idx + 1}: Expected readiness "
                                f"{step.expected_readiness}, got {j_readiness}"
                            ),
                            duration_ms=(time.perf_counter() - start_time) * 1000,
                        )

                    if (
                        step.expected_completed_count is not None
                        and j_completed != step.expected_completed_count
                    ):
                        return ScenarioResult(
                            scenario_id=scenario.id,
                            pack=scenario.pack,
                            family=scenario.family,
                            passed=False,
                            steps_executed=steps_executed,
                            total_steps=total_steps,
                            error_message=(
                                f"Step {idx + 1}: Expected completed "
                                f"{step.expected_completed_count}, got {j_completed}"
                            ),
                            duration_ms=(time.perf_counter() - start_time) * 1000,
                        )
                else:
                    err_json = act_res.json()
                    err_code = err_json.get("error", {}).get("code")
                    if step.expected_error_code and err_code != step.expected_error_code:
                        return ScenarioResult(
                            scenario_id=scenario.id,
                            pack=scenario.pack,
                            family=scenario.family,
                            passed=False,
                            steps_executed=steps_executed,
                            total_steps=total_steps,
                            error_message=(
                                f"Step {idx + 1}: Expected error code "
                                f"{step.expected_error_code}, got {err_code}"
                            ),
                            duration_ms=(time.perf_counter() - start_time) * 1000,
                        )

            elif step.type == "inject_ambiguity":
                async with session_maker() as db:
                    snap_repo = SnapshotRepository(db)
                    journey_repo = JourneyRepository(db)
                    curr_snap = await snap_repo.get_by_id(UUID(current_snapshot_id))
                    if not curr_snap:
                        raise ValueError(f"Snapshot {current_snapshot_id} not found")

                    fields_copy = dict(curr_snap.fields)
                    amb_dict = {
                        "ambiguity_id": step.ambiguity_id,
                        "field": step.field,
                        "reason": step.reason or "Ambiguity flagged during assessment",
                        "question": step.question or "Please confirm field value",
                        "answer_type": step.answer_type or "TEXT",
                    }
                    existing_f = fields_copy.get(step.field, {})
                    fields_copy[step.field] = {
                        **existing_f,
                        "key": step.field,
                        "status": "AMBIGUOUS",
                        "ambiguity": amb_dict,
                    }

                    token = CheckToken(
                        token_id=uuid4(),
                        journey_id=UUID(journey_id),
                        journey_type=scenario.pack,
                        action_id="EVIDENCE_AMBIGUITY_FLAGGED",
                        previous_snapshot_id=curr_snap.id,
                        action_input={},
                        new_values={},
                        direct_fields=[],
                        created_at=datetime.now(UTC),
                    )
                    new_snap = await snap_repo.create(
                        token=token,
                        readiness="NEEDS_REVIEW",
                        fields=fields_copy,
                        goal=curr_snap.goal,
                        pending_clarification=amb_dict,
                    )
                    await journey_repo.update_state(
                        journey_id=UUID(journey_id),
                        current_snapshot_id=new_snap.id,
                        readiness="NEEDS_REVIEW",
                        status="IN_PROGRESS",
                    )
                    await db.commit()
                    current_snapshot_id = str(new_snap.id)

            elif step.type == "clarification":
                clar_payload = {
                    "ambiguity_id": step.ambiguity_id,
                    "field": step.field,
                    "answer": step.answer,
                    "expected_snapshot_id": current_snapshot_id,
                }
                clar_res = await client.post(
                    f"/api/v1/journeys/{journey_id}/clarifications",
                    json=clar_payload,
                    headers=headers,
                )

                if clar_res.status_code != step.expected_status_code:
                    return ScenarioResult(
                        scenario_id=scenario.id,
                        pack=scenario.pack,
                        family=scenario.family,
                        passed=False,
                        steps_executed=steps_executed,
                        total_steps=total_steps,
                        error_message=(
                            f"Step {idx + 1} (clarification): "
                            f"Expected {step.expected_status_code}, "
                            f"got {clar_res.status_code}: {clar_res.text}"
                        ),
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                    )

                if clar_res.status_code == 200:
                    data = clar_res.json()
                    current_snapshot_id = data["journey"]["snapshot_id"]
                    j_ver = data["journey"]["version_number"]
                    j_readiness = data["journey"]["readiness"]

                    if step.expected_version is not None and j_ver != step.expected_version:
                        return ScenarioResult(
                            scenario_id=scenario.id,
                            pack=scenario.pack,
                            family=scenario.family,
                            passed=False,
                            steps_executed=steps_executed,
                            total_steps=total_steps,
                            error_message=(
                                f"Step {idx + 1}: Expected version "
                                f"{step.expected_version}, got {j_ver}"
                            ),
                            duration_ms=(time.perf_counter() - start_time) * 1000,
                        )

                    if (
                        step.expected_readiness is not None
                        and j_readiness != step.expected_readiness
                    ):
                        return ScenarioResult(
                            scenario_id=scenario.id,
                            pack=scenario.pack,
                            family=scenario.family,
                            passed=False,
                            steps_executed=steps_executed,
                            total_steps=total_steps,
                            error_message=(
                                f"Step {idx + 1}: Expected readiness "
                                f"{step.expected_readiness}, got {j_readiness}"
                            ),
                            duration_ms=(time.perf_counter() - start_time) * 1000,
                        )

            elif step.type == "check_recommendation":
                rec_res = await client.get(
                    f"/api/v1/journeys/{journey_id}/recommendation",
                    headers=headers,
                )
                if rec_res.status_code != 200:
                    return ScenarioResult(
                        scenario_id=scenario.id,
                        pack=scenario.pack,
                        family=scenario.family,
                        passed=False,
                        steps_executed=steps_executed,
                        total_steps=total_steps,
                        error_message=(
                            f"Step {idx + 1}: Recommendation query failed: {rec_res.status_code}"
                        ),
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                    )

                rec_data = rec_res.json()
                rec = rec_data.get("recommendation")
                if step.expected_recommended_action_id and rec:
                    rec_act = rec.get("action_id")
                    if isinstance(step.expected_recommended_action_id, list):
                        if rec_act not in step.expected_recommended_action_id:
                            return ScenarioResult(
                                scenario_id=scenario.id,
                                pack=scenario.pack,
                                family=scenario.family,
                                passed=False,
                                steps_executed=steps_executed,
                                total_steps=total_steps,
                                error_message=(
                                    f"Step {idx + 1}: Recommended action {rec_act} "
                                    f"not in {step.expected_recommended_action_id}"
                                ),
                                duration_ms=(time.perf_counter() - start_time) * 1000,
                            )
                    elif rec_act != step.expected_recommended_action_id:
                        return ScenarioResult(
                            scenario_id=scenario.id,
                            pack=scenario.pack,
                            family=scenario.family,
                            passed=False,
                            steps_executed=steps_executed,
                            total_steps=total_steps,
                            error_message=(
                                f"Step {idx + 1}: Expected recommendation "
                                f"{step.expected_recommended_action_id}, got {rec_act}"
                            ),
                            duration_ms=(time.perf_counter() - start_time) * 1000,
                        )

            steps_executed += 1

        return ScenarioResult(
            scenario_id=scenario.id,
            pack=scenario.pack,
            family=scenario.family,
            passed=True,
            steps_executed=steps_executed,
            total_steps=total_steps,
            duration_ms=(time.perf_counter() - start_time) * 1000,
        )

    except Exception as exc:
        return ScenarioResult(
            scenario_id=scenario.id,
            pack=scenario.pack,
            family=scenario.family,
            passed=False,
            steps_executed=steps_executed,
            total_steps=total_steps,
            error_message=f"Unhandled exception: {exc!s}",
            duration_ms=(time.perf_counter() - start_time) * 1000,
        )


def format_matrix_table(results: list[ScenarioResult]) -> str:
    packs = ["LENDING", "INSURANCE", "CREDIT_CARD", "KYC", "ACCOUNT_OPENING", "INVESTMENT"]
    families = [
        "GOLDEN",
        "MULTI_BLOCKER",
        "AMBIGUITY_CONFLICT",
        "ALTERNATE_OR_OVERRIDE",
        "INVALID_ACTION",
        "STALE_ACTION",
    ]

    # Map of (pack, family) -> ScenarioResult
    res_map = {(r.pack, r.family): r for r in results}

    col_headers = (
        f"{'PACK':<18} {'GOLDEN':<10} {'MULTI_BLK':<11} {'AMBIGUITY':<11} "
        f"{'ALTERNATE':<11} {'INVALID':<9} {'STALE':<9} {'STATUS':<7}\n"
    )

    header = (
        "=" * 96
        + "\n"
        + "PAYTMFLOW SCENARIO EVALUATION MATRIX (36 Scenarios: 6 Packs x 6 Families)\n"
        + "=" * 96
        + "\n"
        + col_headers
        + "-" * 96
    )

    lines = [header]
    total_passed = 0
    total_scenarios = len(packs) * len(families)

    for p in packs:
        row_str = f"{p:<18} "
        row_pass = 0
        for f in families:
            res = res_map.get((p, f))
            if res and res.passed:
                row_str += f"{'PASS':<10} " if f == "GOLDEN" else ""
                if f == "MULTI_BLOCKER":
                    row_str += f"{'PASS':<11} "
                elif f == "AMBIGUITY_CONFLICT":
                    row_str += f"{'PASS':<11} "
                elif f == "ALTERNATE_OR_OVERRIDE":
                    row_str += f"{'PASS':<11} "
                elif f in ["INVALID_ACTION", "STALE_ACTION"]:
                    row_str += f"{'PASS':<9} "
                row_pass += 1
                total_passed += 1
            else:
                tag = "FAIL" if res else "N/A"
                if f == "GOLDEN":
                    row_str += f"{tag:<10} "
                elif f in ["MULTI_BLOCKER", "AMBIGUITY_CONFLICT", "ALTERNATE_OR_OVERRIDE"]:
                    row_str += f"{tag:<11} "
                else:
                    row_str += f"{tag:<9} "
        row_str += f"{row_pass}/6"
        lines.append(row_str)

    lines.append("-" * 96)
    pass_pct = (total_passed / total_scenarios) * 100.0 if total_scenarios > 0 else 0.0
    lines.append(f"TOTAL PASSED: {total_passed} / {total_scenarios} ({pass_pct:.1f}%)")
    lines.append("=" * 96)

    # If any failures, append details
    failures = [r for r in results if not r.passed]
    if failures:
        lines.append("\nFAILED SCENARIOS DETAIL:")
        for f in failures:
            lines.append(f"  - [{f.pack} - {f.family}] {f.scenario_id}: {f.error_message}")

    return "\n".join(lines)


async def _create_scenario_engine() -> Any:
    """Connect to PostgreSQL for the scenario matrix.

    Falls back to SQLite in-memory ONLY when REQUIRE_POSTGRES is not set, and
    always warns loudly when it does - SQLite does not enforce foreign keys the
    way PostgreSQL does, which previously hid a real defect (B17/B30) from every
    scenario run. Set REQUIRE_POSTGRES=1 to fail hard instead.
    """
    require_postgres = os.environ.get("REQUIRE_POSTGRES", "").lower() in ("1", "true", "yes")

    pg_url = settings.DATABASE_URL
    if pg_url.startswith("postgresql://"):
        pg_url = pg_url.replace("postgresql://", "postgresql+psycopg://", 1)

    try:
        candidate = create_async_engine(pg_url, echo=False)
        async with candidate.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return candidate
    except Exception as exc:
        if require_postgres:
            print(
                f"REQUIRE_POSTGRES=1 but PostgreSQL is unavailable at "
                f"{settings.DATABASE_URL!r}: {exc}. Start it with "
                f"`docker compose up -d postgres` before running the scenario matrix.",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
        message = (
            "PostgreSQL unavailable - the scenario matrix is falling back to an "
            "in-memory SQLite engine. SQLite does NOT enforce foreign keys the "
            "way PostgreSQL does; this can hide real defects (see B17/B30). Run "
            "with REQUIRE_POSTGRES=1 against a real PostgreSQL instance before "
            "trusting this run."
        )
        print(f"\n\033[93mWARNING: {message}\033[0m", file=sys.stderr)
        warnings.warn(message, stacklevel=2)
        return create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


async def run_all_scenarios(
    scenarios_dir: Path | str | None = None,
) -> tuple[list[ScenarioResult], str]:
    pack_registry.load_all()

    test_engine = await _create_scenario_engine()
    async with test_engine.begin() as conn:
        # Recreate schema cleanly - matters for a persistent real Postgres, a
        # no-op for a fresh in-memory SQLite engine.
        await conn.run_sync(Base.metadata.drop_all)
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

    scenarios = load_all_scenarios(scenarios_dir)
    results: list[ScenarioResult] = []

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for scen in scenarios:
            res = await run_scenario(scen, client, session_maker)
            results.append(res)

    app.dependency_overrides.clear()
    await test_engine.dispose()

    matrix_str = format_matrix_table(results)
    return results, matrix_str


def main():
    results, matrix_str = asyncio.run(run_all_scenarios())
    print(matrix_str)
    all_passed = all(r.passed for r in results) and len(results) == 36
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
