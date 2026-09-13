import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.ai.guardrails import GuardrailedAIProvider
from app.ai.llm import LLMProvider
from app.ai.models import ActionRankingResult, AIInterpretationResult
from app.ai.provider import get_ai_provider
from app.config import settings
from app.core.models import CoreReadiness, CoreSnapshot
from app.packs.contract import JourneyPackManifest
from app.packs.registry import pack_registry


@pytest.fixture
def sample_manifest() -> JourneyPackManifest:
    manifest = pack_registry.get_pack("LENDING")
    assert manifest is not None
    return manifest


def _create_mock_response(data: dict, status_code: int = 200) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=data)
    return mock_resp


@pytest.mark.asyncio
async def test_get_ai_provider_returns_llm_provider(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "llm")
    monkeypatch.setattr(settings, "AI_API_KEY", "test-key")

    provider = get_ai_provider(guardrailed=True)
    assert isinstance(provider, GuardrailedAIProvider)
    assert isinstance(provider.inner, LLMProvider)

    raw_provider = get_ai_provider(guardrailed=False)
    assert isinstance(raw_provider, LLMProvider)


@pytest.mark.asyncio
async def test_llm_parse_goal_success(sample_manifest):
    llm = LLMProvider(api_key="mock-key", model="gpt-4o-mini")

    mock_llm_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"loan_amount": 250000, "loan_purpose": "HOME_RENOVATION"}
                    )
                }
            }
        ]
    }

    mock_resp = _create_mock_response(mock_llm_response)
    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await llm.parse_goal(
            journey_type="LENDING",
            natural_language="Need 2.5 lakh for home renovation",
            goal_schema=sample_manifest.goal_schema,
        )

        assert res["loan_amount"] == 250000
        assert res["loan_purpose"] == "HOME_RENOVATION"


@pytest.mark.asyncio
async def test_llm_reconcile_evidence_success(sample_manifest):
    llm = LLMProvider(api_key="mock-key")

    mock_evidence_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "verified": True,
                            "confidence": 0.95,
                            "detected": [
                                {
                                    "key": "monthly_income",
                                    "label": "Monthly Net Income",
                                    "display_value": "₹85,000",
                                    "value": 85000,
                                }
                            ],
                            "summary": "Salary slip verifies monthly net earnings of ₹85,000.",
                            "conflicts": [],
                            "raw_values": {"monthly_income": 85000},
                        }
                    )
                }
            }
        ]
    }

    mock_resp = _create_mock_response(mock_evidence_response)
    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await llm.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text="Salary slip for John Doe Net Pay: 85000",
            manifest=sample_manifest,
        )

        assert isinstance(res, AIInterpretationResult)
        assert res.verified is True
        assert res.confidence == 0.95
        assert len(res.detected) == 1
        assert res.detected[0].value == 85000


@pytest.mark.asyncio
async def test_llm_select_action_success(sample_manifest):
    llm = LLMProvider(api_key="mock-key")

    mock_ranking_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "recommended_action_id": "UPLOAD_INCOME_PROOF",
                            "why": "Income verification is required for customized loan terms.",
                            "ranking_order": ["UPLOAD_INCOME_PROOF", "SUBMIT_EMPLOYMENT_INFO"],
                        }
                    )
                }
            }
        ]
    }

    snapshot = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=uuid4(),
        journey_type="LENDING",
        version_number=1,
        readiness=CoreReadiness.NOT_READY,
        fields={},
        goal={},
    )

    mock_resp = _create_mock_response(mock_ranking_response)
    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await llm.select_action(
            snapshot=snapshot,
            candidate_actions=sample_manifest.actions,
            manifest=sample_manifest,
        )

        assert isinstance(res, ActionRankingResult)
        assert res.recommended_action_id == "UPLOAD_INCOME_PROOF"
        assert "Income verification" in res.why


@pytest.mark.asyncio
async def test_llm_fallback_on_no_api_key(sample_manifest):
    # Empty api_key -> falls back to MockAI
    llm = LLMProvider(api_key="")

    res = await llm.parse_goal(
        journey_type="LENDING",
        natural_language="I need a 3 lakh personal loan for medical emergency",
        goal_schema=sample_manifest.goal_schema,
    )
    assert res["loan_amount"] == 300000
    assert res["loan_purpose"] == "MEDICAL_EXPENSES"


@pytest.mark.asyncio
async def test_llm_fallback_on_network_error(sample_manifest):
    llm = LLMProvider(api_key="mock-key")

    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
        res = await llm.parse_goal(
            journey_type="LENDING",
            natural_language="Need 2 lakh loan for home renovation",
            goal_schema=sample_manifest.goal_schema,
        )
        assert res["loan_amount"] == 200000
        assert res["loan_purpose"] == "HOME_RENOVATION"


@pytest.mark.asyncio
async def test_llm_fallback_on_malformed_json(sample_manifest):
    llm = LLMProvider(api_key="mock-key")

    mock_bad_response = {
        "choices": [{"message": {"content": "This is not valid json content {bad_key: "}}]
    }

    mock_resp = _create_mock_response(mock_bad_response)
    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await llm.parse_goal(
            journey_type="LENDING",
            natural_language="Need 1 lakh loan for medical emergency",
            goal_schema=sample_manifest.goal_schema,
        )
        assert res["loan_amount"] == 100000
        assert res["loan_purpose"] == "MEDICAL_EXPENSES"


@pytest.mark.asyncio
async def test_llm_explain_with_guardrail_sanitization(sample_manifest):
    llm = LLMProvider(api_key="mock-key")
    guardrailed = GuardrailedAIProvider(inner_provider=llm)

    # If LLM produces prohibited claims (e.g. "approved", "credit score")
    mock_llm_response = {
        "choices": [
            {
                "message": {
                    "content": "Your loan has been approved and guaranteed with high credit score!"
                }
            }
        ]
    }

    mock_resp = _create_mock_response(mock_llm_response)
    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        explanation = await guardrailed.explain(
            field_key="monthly_income",
            from_status="BLOCKED",
            to_status="SATISFIED",
            action_id="UPLOAD_INCOME_PROOF",
            manifest=sample_manifest,
        )

        # Prohibited claim was detected and sanitized to safe fallback
        assert "approved" not in explanation.lower()
        assert "guaranteed" not in explanation.lower()
        assert "credit score" not in explanation.lower()
