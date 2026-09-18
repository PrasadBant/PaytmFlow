import pytest

from app.ai import MockAI, get_ai_provider
from app.ai.guardrails import GuardrailedAIProvider
from app.ai.models import ActionRankingResult, AIInterpretationResult
from app.config import settings
from app.core.models import CoreFieldState, CoreFieldStatus, CoreReadiness, CoreSnapshot
from app.packs.registry import pack_registry
from app.schemas.enums import JourneyType

BANNED_WORDS = [
    "approved",
    "approval",
    "probability",
    "credit score",
    "eligibility score",
    "readiness score",
    "guaranteed",
]


@pytest.fixture(autouse=True)
def load_manifests(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "mock")
    pack_registry.load_all()


@pytest.mark.asyncio
async def test_get_ai_provider_returns_mock_ai():
    provider = get_ai_provider()
    assert isinstance(provider, GuardrailedAIProvider)
    assert isinstance(provider.inner, MockAI)

    raw_provider = get_ai_provider(guardrailed=False)
    assert isinstance(raw_provider, MockAI)


@pytest.mark.asyncio
async def test_parse_goal_all_six_packs():
    ai = MockAI()

    # 1. Lending
    lending_pack = pack_registry.get_pack(JourneyType.LENDING)
    assert lending_pack is not None
    goal_lending = await ai.parse_goal(
        journey_type="LENDING",
        natural_language="Need 2.5 lakh personal loan for home renovation for 24 months",
        goal_schema=lending_pack.goal_schema,
    )
    assert goal_lending["loan_amount"] == 250000
    assert goal_lending["loan_purpose"] == "HOME_RENOVATION"
    assert goal_lending["tenure_months"] == 24

    # 2. Insurance
    insurance_pack = pack_registry.get_pack(JourneyType.INSURANCE)
    assert insurance_pack is not None
    goal_ins = await ai.parse_goal(
        journey_type="INSURANCE",
        natural_language="Looking for 500000 individual health insurance cover",
        goal_schema=insurance_pack.goal_schema,
    )
    assert goal_ins["sum_insured"] == 500000
    assert goal_ins["policy_type"] == "INDIVIDUAL"

    # 3. Credit Card
    cc_pack = pack_registry.get_pack(JourneyType.CREDIT_CARD)
    assert cc_pack is not None
    goal_cc = await ai.parse_goal(
        journey_type="CREDIT_CARD",
        natural_language="Want a cashback credit card",
        goal_schema=cc_pack.goal_schema,
    )
    assert "card_variant" in goal_cc
    assert goal_cc["card_variant"] == "CASHBACK"

    # 4. KYC
    kyc_pack = pack_registry.get_pack(JourneyType.KYC)
    assert kyc_pack is not None
    goal_kyc = await ai.parse_goal(
        journey_type="KYC",
        natural_language="KYC verification for digital wallet",
        goal_schema=kyc_pack.goal_schema,
    )
    assert "kyc_purpose" in goal_kyc
    assert goal_kyc["kyc_purpose"] == "LIMIT_UPGRADE"

    # 5. Account Opening
    ao_pack = pack_registry.get_pack(JourneyType.ACCOUNT_OPENING)
    assert ao_pack is not None
    goal_ao = await ai.parse_goal(
        journey_type="ACCOUNT_OPENING",
        natural_language="Open a savings account",
        goal_schema=ao_pack.goal_schema,
    )
    assert "account_type" in goal_ao
    assert goal_ao["account_type"] == "DIGITAL_SAVINGS"

    # 6. Investment
    inv_pack = pack_registry.get_pack(JourneyType.INVESTMENT)
    assert inv_pack is not None
    goal_inv = await ai.parse_goal(
        journey_type="INVESTMENT",
        natural_language="Monthly SIP target amount 100000",
        goal_schema=inv_pack.goal_schema,
    )
    assert goal_inv["investment_mode"] == "MONTHLY_SIP"
    assert goal_inv["target_amount"] == 100000


@pytest.mark.asyncio
async def test_reconcile_evidence_all_six_packs():
    ai = MockAI()

    for jtype in JourneyType:
        pack = pack_registry.get_pack(jtype)
        assert pack is not None
        for mapping in pack.evidence_mappings:
            res = await ai.reconcile_evidence(
                doc_type=mapping.doc_type,
                extracted_text=f"Sample document content for {mapping.doc_type}",
                manifest=pack,
            )
            assert isinstance(res, AIInterpretationResult)
            assert res.verified is True
            assert res.confidence >= mapping.confidence_threshold
            assert len(res.detected) > 0
            assert len(res.summary) > 0
            assert len(res.conflicts) == 0

            # Verify no banned words in summary
            summary_lower = res.summary.lower()
            for w in BANNED_WORDS:
                assert w not in summary_lower, f"Found banned word '{w}' in summary"

            # Real-browser QA regression: `summary` is rendered verbatim on
            # Screen 7 (`ai-summary-text`); frontend/CLAUDE.md rule 1 is
            # absolute - "NEVER render a percentage" - and the live app's
            # real summary text used to read "...with high confidence
            # (96%)." for exactly this MockAI code path.
            assert "%" not in res.summary, f"Found a raw percentage in summary: {res.summary!r}"


@pytest.mark.asyncio
async def test_reconcile_evidence_conflict_detection():
    ai = MockAI()
    lending_pack = pack_registry.get_pack(JourneyType.LENDING)
    assert lending_pack is not None

    res = await ai.reconcile_evidence(
        doc_type="BANK_STATEMENT",
        extracted_text="Bank statement with average credit 62000 causing mismatch with salary slip",
        manifest=lending_pack,
        existing_fields={"monthly_income": 85000},
    )
    assert isinstance(res, AIInterpretationResult)
    assert res.verified is False
    assert len(res.conflicts) == 1
    assert res.conflicts[0].ambiguity_id == "INCOME_MISMATCH"
    assert res.conflicts[0].field == "monthly_income"


@pytest.mark.asyncio
async def test_select_action_and_explain():
    ai = MockAI()
    lending_pack = pack_registry.get_pack(JourneyType.LENDING)
    assert lending_pack is not None

    snapshot = CoreSnapshot(
        snapshot_id=lending_pack.metadata.journey_type,
        journey_id=lending_pack.metadata.journey_type,
        journey_type="LENDING",
        version_number=1,
        readiness=CoreReadiness.NOT_READY,
        fields={
            "kyc_verified": CoreFieldState(
                key="kyc_verified",
                label="KYC",
                status=CoreFieldStatus.SATISFIED,
                mandatory=True,
            )
        },
    )

    ranking = await ai.select_action(
        snapshot=snapshot,
        candidate_actions=lending_pack.actions,
        manifest=lending_pack,
    )
    assert isinstance(ranking, ActionRankingResult)
    assert ranking.recommended_action_id == lending_pack.actions[0].action_id
    assert len(ranking.why) > 0
    assert len(ranking.ranking_order) == len(lending_pack.actions)

    # Test explain
    explanation = await ai.explain(
        field_key="monthly_income",
        from_status="BLOCKED",
        to_status="SATISFIED",
        action_id="UPLOAD_INCOME_PROOF",
        manifest=lending_pack,
    )
    assert isinstance(explanation, str)
    assert "verified" in explanation.lower() or "satisfied" in explanation.lower()

    for w in BANNED_WORDS:
        assert w not in explanation.lower()
