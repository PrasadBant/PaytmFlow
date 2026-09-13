import json
from pathlib import Path

import pytest

from app.schemas import (
    ActionResponse,
    ErrorEnvelope,
    EvidenceResponse,
    JourneyPackDetail,
    JourneyPacksListResponse,
    JourneysListResponse,
    JourneyStateResponse,
    RecommendationResponse,
    SessionResponse,
)

FIXTURES_DIR = Path(__file__).parents[3] / "contract" / "fixtures"

FIXTURE_SCHEMA_MAP = {
    "session.json": SessionResponse,
    "packs.list.json": JourneyPacksListResponse,
    "packs.LENDING.json": JourneyPackDetail,
    "packs.INSURANCE.json": JourneyPackDetail,
    "packs.CREDIT_CARD.json": JourneyPackDetail,
    "packs.KYC.json": JourneyPackDetail,
    "packs.ACCOUNT_OPENING.json": JourneyPackDetail,
    "packs.INVESTMENT.json": JourneyPackDetail,
    "lending/v1.state.json": JourneyStateResponse,
    "lending/v1.recommendation.json": RecommendationResponse,
    "lending/evidence.salary_slip.json": EvidenceResponse,
    "lending/v2.action.json": ActionResponse,
    "lending/v3.recommendation.json": RecommendationResponse,
    "lending/evidence.bank_statement.json": EvidenceResponse,
    "lending/v4.clarification.json": ActionResponse,
    "lending/v5.ready.json": JourneyStateResponse,
    "lending/error.stale.json": ErrorEnvelope,
    "lending/error.invalid.json": ErrorEnvelope,
    "lending/error.deadend.json": ErrorEnvelope,
    "insurance/v1.state.json": JourneyStateResponse,
    "insurance/v1.recommendation.json": RecommendationResponse,
    "insurance/ready.json": JourneyStateResponse,
    "credit_card/v1.state.json": JourneyStateResponse,
    "credit_card/v1.recommendation.json": RecommendationResponse,
    "credit_card/ready.json": JourneyStateResponse,
    "kyc/v1.state.json": JourneyStateResponse,
    "kyc/v1.recommendation.json": RecommendationResponse,
    "kyc/ready.json": JourneyStateResponse,
    "account_opening/v1.state.json": JourneyStateResponse,
    "account_opening/v1.recommendation.json": RecommendationResponse,
    "account_opening/ready.json": JourneyStateResponse,
    "investment/v1.state.json": JourneyStateResponse,
    "investment/v1.recommendation.json": RecommendationResponse,
    "investment/ready.json": JourneyStateResponse,
    "journeys.list.json": JourneysListResponse,
}


@pytest.mark.parametrize("rel_path,schema_cls", FIXTURE_SCHEMA_MAP.items())
def test_fixture_validates_against_schema(rel_path, schema_cls):
    file_path = FIXTURES_DIR / rel_path
    assert file_path.exists(), f"Fixture file missing: {file_path}"
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    validated = schema_cls.model_validate(data)
    assert validated is not None


def test_no_score_in_any_fixture():
    banned_words = [
        "approved",
        "approval",
        "probability",
        "credit score",
        "eligibility score",
        "readiness score",
        "guaranteed",
    ]
    for file_path in FIXTURES_DIR.glob("**/*.json"):
        content = file_path.read_text(encoding="utf-8").lower()
        for word in banned_words:
            assert word not in content, f"Banned word '{word}' found in fixture {file_path.name}"
