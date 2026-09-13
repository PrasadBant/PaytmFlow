import asyncio
from typing import Any
from uuid import uuid4

import pytest

from app.ai.guardrails import (
    BANNED_WORDS,
    GuardrailedAIProvider,
    sanitize_text,
    scan_prohibited_claims,
    wrap_untrusted,
)
from app.ai.mock import MockAI
from app.ai.models import ActionRankingResult, AIInterpretationResult
from app.core.models import CoreFieldState, CoreFieldStatus, CoreReadiness, CoreSnapshot
from app.packs.contract import ActionSpec, GoalFieldSpec, JourneyPackManifest, JourneyType
from app.packs.registry import pack_registry


class DelayProvider(MockAI):
    """Provider that deliberately hangs to trigger timeouts."""

    async def parse_goal(
        self,
        journey_type: str,
        natural_language: str,
        goal_schema: list[GoalFieldSpec],
    ) -> dict[str, Any]:
        await asyncio.sleep(0.5)
        return await super().parse_goal(journey_type, natural_language, goal_schema)

    async def reconcile_evidence(
        self,
        doc_type: str,
        extracted_text: str,
        manifest: JourneyPackManifest,
        existing_fields: dict[str, Any] | None = None,
    ) -> AIInterpretationResult:
        await asyncio.sleep(0.5)
        return await super().reconcile_evidence(doc_type, extracted_text, manifest, existing_fields)

    async def select_action(
        self,
        snapshot: CoreSnapshot,
        candidate_actions: list[ActionSpec],
        manifest: JourneyPackManifest,
    ) -> ActionRankingResult:
        await asyncio.sleep(0.5)
        return await super().select_action(snapshot, candidate_actions, manifest)

    async def explain(
        self,
        field_key: str,
        from_status: str,
        to_status: str,
        action_id: str | None,
        manifest: JourneyPackManifest,
    ) -> str:
        await asyncio.sleep(0.5)
        return await super().explain(field_key, from_status, to_status, action_id, manifest)


class MalformedProvider(MockAI):
    """Provider that returns malformed output or invented action IDs."""

    async def reconcile_evidence(
        self,
        doc_type: str,
        extracted_text: str,
        manifest: JourneyPackManifest,
        existing_fields: dict[str, Any] | None = None,
    ) -> Any:
        # Returns invalid schema shape
        return {"invalid_key": 12345}

    async def select_action(
        self,
        snapshot: CoreSnapshot,
        candidate_actions: list[ActionSpec],
        manifest: JourneyPackManifest,
    ) -> ActionRankingResult:
        # Returns an invented action ID not in candidate_actions
        return ActionRankingResult(
            recommended_action_id="INVENTED_MAGIC_ACTION_ID",
            why="This is a guaranteed approval with high credit score!",
            ranking_order=["INVENTED_MAGIC_ACTION_ID"],
        )

    async def explain(
        self,
        field_key: str,
        from_status: str,
        to_status: str,
        action_id: str | None,
        manifest: JourneyPackManifest,
    ) -> str:
        return "Your loan has guaranteed approval with 100% probability and 850 credit score!"


def test_wrap_untrusted_truncation_and_tags():
    raw_text = "A" * 12000
    wrapped = wrap_untrusted(raw_text, max_chars=8000)

    assert "<untrusted_document>" in wrapped
    assert "</untrusted_document>" in wrapped
    assert "[SYSTEM INSTRUCTION:" in wrapped
    # Inner content truncated to 8000 chars
    assert "A" * 8000 in wrapped
    assert "A" * 8001 not in wrapped


def test_scan_and_sanitize_banned_words():
    manifest = pack_registry.get_pack(JourneyType.LENDING)
    assert manifest is not None

    for banned in BANNED_WORDS:
        text = f"This document ensures your application is {banned}."
        violated, matched = scan_prohibited_claims(text, manifest)
        assert violated is True
        assert banned in matched

        sanitized = sanitize_text(text, fallback_copy="Safe fallback", manifest=manifest)
        assert sanitized == "Safe fallback"


@pytest.mark.asyncio
async def test_guardrail_timeout_fallback():
    # Set a tiny timeout (0.05s) to trigger timeout on DelayProvider (which sleeps 0.5s)
    guard = GuardrailedAIProvider(inner_provider=DelayProvider(), timeout_seconds=0.05)
    manifest = pack_registry.get_pack(JourneyType.LENDING)
    assert manifest is not None

    # 1. parse_goal timeout fallback
    goal = await guard.parse_goal(
        journey_type="LENDING",
        natural_language="Need 200000",
        goal_schema=manifest.goal_schema,
    )
    assert "loan_amount" in goal
    assert goal["loan_amount"] >= 25000

    # 2. reconcile_evidence timeout fallback
    res = await guard.reconcile_evidence(
        doc_type="salary_slip",
        extracted_text="Some text",
        manifest=manifest,
    )
    assert res.verified is False
    assert res.confidence == 0.0
    assert "unavailable" in res.summary.lower()

    # 3. select_action timeout fallback
    snap = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=uuid4(),
        version_number=1,
        journey_type=JourneyType.LENDING,
        fields={
            "income_verified": CoreFieldState(
                key="income_verified",
                label="Income Verification",
                status=CoreFieldStatus.BLOCKED,
            )
        },
        readiness=CoreReadiness.NOT_READY,
    )
    action_res = await guard.select_action(
        snapshot=snap,
        candidate_actions=manifest.actions[:2],
        manifest=manifest,
    )
    assert action_res.recommended_action_id == manifest.actions[0].action_id

    # 4. explain timeout fallback
    exp = await guard.explain(
        field_key="income_verified",
        from_status="BLOCKED",
        to_status="SATISFIED",
        action_id=manifest.actions[0].action_id,
        manifest=manifest,
    )
    assert len(exp) > 0


@pytest.mark.asyncio
async def test_guardrail_fault_injection_malformed_and_invented_action():
    guard = GuardrailedAIProvider(inner_provider=MalformedProvider(), timeout_seconds=1.0)
    manifest = pack_registry.get_pack(JourneyType.LENDING)
    assert manifest is not None

    # 1. Malformed evidence output -> falls back to safe result
    res = await guard.reconcile_evidence(
        doc_type="salary_slip",
        extracted_text="Salary details",
        manifest=manifest,
    )
    assert res.verified is False
    assert res.confidence == 0.0

    # 2. Invented action_id -> rejected and replaced with valid candidate
    snap = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=uuid4(),
        version_number=1,
        journey_type=JourneyType.LENDING,
        fields={},
        readiness=CoreReadiness.NOT_READY,
    )
    candidate_actions = manifest.actions[:2]
    action_res = await guard.select_action(
        snapshot=snap,
        candidate_actions=candidate_actions,
        manifest=manifest,
    )
    assert action_res.recommended_action_id == candidate_actions[0].action_id
    assert "INVENTED_MAGIC_ACTION_ID" not in action_res.recommended_action_id

    # 3. Prohibited claims in why and explain are sanitized
    for banned in BANNED_WORDS:
        assert banned not in action_res.why.lower()

    exp = await guard.explain(
        field_key="income_verified",
        from_status="BLOCKED",
        to_status="SATISFIED",
        action_id=manifest.actions[0].action_id,
        manifest=manifest,
    )
    for banned in BANNED_WORDS:
        assert banned not in exp.lower()
