import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.guardrails import GuardrailedAIProvider
from app.ai.local_ml import LocalMLProvider
from app.ai.models import AIInterpretationResult
from app.ai.provider import get_ai_provider
from app.ai.sarvam import SarvamProvider
from app.ai.sarvam_client import (
    SarvamClient,
    SarvamInvalidResponseError,
    SarvamProviderError,
    SarvamRateLimitError,
    SarvamTimeoutError,
)
from app.config import settings
from app.packs.contract import JourneyPackManifest
from app.packs.registry import pack_registry


@pytest.fixture
def sample_manifest() -> JourneyPackManifest:
    manifest = pack_registry.get_pack("LENDING")
    assert manifest is not None
    return manifest


def _zip_extraction(
    values: dict,
    field_confidence: dict | None = None,
    no_extractable_content: bool = False,
) -> bytes:
    """Builds a real in-memory ZIP matching Sarvam's actual Extract job
    result shape (verified live against a real account - see
    app/ai/sarvam.py's module docstring): a ZIP containing extraction.json
    with {"data", "field_confidence", "field_sources",
    "no_extractable_content"}."""
    payload = {
        "data": values,
        "field_confidence": field_confidence or {},
        "field_sources": {},
        "no_extractable_content": no_extractable_content,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("extraction.json", json.dumps(payload))
    return buf.getvalue()


def _mock_response(
    data: dict | None = None, status_code: int = 200, content: bytes | None = None
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=data or {})
    resp.content = content if content is not None else json.dumps(data or {}).encode("utf-8")
    return resp


def test_get_ai_provider_returns_sarvam_provider(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")

    provider = get_ai_provider(guardrailed=True)
    assert isinstance(provider, GuardrailedAIProvider)
    assert isinstance(provider.inner, SarvamProvider)
    assert provider.timeout_seconds == float(settings.SARVAM_TIMEOUT_SECONDS)

    raw_provider = get_ai_provider(guardrailed=False)
    assert isinstance(raw_provider, SarvamProvider)
    assert isinstance(raw_provider.fallback_provider, LocalMLProvider)


@pytest.mark.asyncio
async def test_reconcile_evidence_success(sample_manifest, monkeypatch):
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")
    provider = SarvamProvider(client=SarvamClient(api_key="test-key"))

    post_resp = _mock_response({"job_id": "job-1", "status": "processing"})
    status_resp = _mock_response(
        {
            "job_id": "job-1",
            "status": "completed",
            "usage": {"pages_total": 1, "pages_succeeded": 1},
        }
    )
    download_url_resp = _mock_response({"url": "https://cdn.sarvam.ai/result.json"})
    result_resp = _mock_response(
        content=_zip_extraction({"monthly_income": 66500}, {"monthly_income": 1})
    )

    with (
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_resp)),
        patch(
            "httpx.AsyncClient.get",
            new=AsyncMock(side_effect=[status_resp, download_url_resp, result_resp]),
        ),
    ):
        res = await provider.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text="Salary slip for John Doe Net Pay: 66500",
            manifest=sample_manifest,
            raw_file=b"%PDF-fake-bytes",
            filename="salary_slip.pdf",
        )

    assert isinstance(res, AIInterpretationResult)
    assert res.provider == "sarvam"
    assert res.verified is True
    assert res.raw_values.get("monthly_income") == 66500
    assert any(d.key == "monthly_income" for d in res.detected)


@pytest.mark.asyncio
async def test_reconcile_evidence_partial_completion_treated_as_success(
    sample_manifest, monkeypatch
):
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")
    provider = SarvamProvider(client=SarvamClient(api_key="test-key"))

    post_resp = _mock_response({"job_id": "job-2", "status": "processing"})
    status_resp = _mock_response(
        {
            "job_id": "job-2",
            "status": "partially_completed",
            "usage": {"pages_total": 2, "pages_succeeded": 1, "pages_failed": 1},
        }
    )
    download_url_resp = _mock_response({"url": "https://cdn.sarvam.ai/result.json"})
    # No field_confidence given - overall confidence falls back to the
    # pages_succeeded/pages_total ratio (0.5), exercising that fallback path.
    result_resp = _mock_response(content=_zip_extraction({"monthly_income": 66500}))

    with (
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_resp)),
        patch(
            "httpx.AsyncClient.get",
            new=AsyncMock(side_effect=[status_resp, download_url_resp, result_resp]),
        ),
    ):
        res = await provider.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text="text",
            manifest=sample_manifest,
            raw_file=b"bytes",
            filename="f.pdf",
        )

    assert res.provider == "sarvam"
    # partially_completed is not fully verified, but is not a hard failure either.
    assert res.confidence == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_reconcile_evidence_invalid_response_falls_back(sample_manifest, monkeypatch):
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")
    provider = SarvamProvider(client=SarvamClient(api_key="test-key"))

    post_resp = _mock_response({"job_id": "job-3", "status": "processing"})
    status_resp = _mock_response({"job_id": "job-3", "status": "completed"})
    download_url_resp = _mock_response({"url": "https://cdn.sarvam.ai/result.json"})
    # Not a valid ZIP archive -> SarvamInvalidResponseError -> fallback
    bad_result_resp = _mock_response(content=b"not a zip file at all")

    with (
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_resp)),
        patch(
            "httpx.AsyncClient.get",
            new=AsyncMock(side_effect=[status_resp, download_url_resp, bad_result_resp]),
        ),
    ):
        res = await provider.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text="Salary slip for John Doe Net Pay: 66500",
            manifest=sample_manifest,
            raw_file=b"bytes",
            filename="f.pdf",
        )

    assert res.provider == "local_ml"


@pytest.mark.asyncio
async def test_reconcile_evidence_failed_job_falls_back(sample_manifest, monkeypatch):
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")
    provider = SarvamProvider(client=SarvamClient(api_key="test-key"))

    post_resp = _mock_response({"job_id": "job-4", "status": "processing"})
    status_resp = _mock_response({"job_id": "job-4", "status": "failed"})

    with (
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_resp)),
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=status_resp)),
    ):
        res = await provider.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text="Salary slip for John Doe Net Pay: 66500",
            manifest=sample_manifest,
            raw_file=b"bytes",
            filename="f.pdf",
        )

    assert res.provider == "local_ml"


@pytest.mark.asyncio
async def test_reconcile_evidence_timeout_falls_back(sample_manifest, monkeypatch):
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")
    provider = SarvamProvider(client=SarvamClient(api_key="test-key"))

    with patch.object(
        provider.client, "create_extract_job", side_effect=SarvamTimeoutError("timed out")
    ):
        res = await provider.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text="Salary slip for John Doe Net Pay: 66500",
            manifest=sample_manifest,
            raw_file=b"bytes",
            filename="f.pdf",
        )

    assert res.provider == "local_ml"


@pytest.mark.asyncio
async def test_reconcile_evidence_rate_limit_falls_back(sample_manifest, monkeypatch):
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")
    provider = SarvamProvider(client=SarvamClient(api_key="test-key"))

    with patch.object(
        provider.client, "create_extract_job", side_effect=SarvamRateLimitError("429")
    ):
        res = await provider.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text="Salary slip for John Doe Net Pay: 66500",
            manifest=sample_manifest,
            raw_file=b"bytes",
            filename="f.pdf",
        )

    assert res.provider == "local_ml"


@pytest.mark.asyncio
async def test_reconcile_evidence_provider_error_falls_back(sample_manifest, monkeypatch):
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")
    provider = SarvamProvider(client=SarvamClient(api_key="test-key"))

    with patch.object(
        provider.client, "create_extract_job", side_effect=SarvamProviderError("5xx")
    ):
        res = await provider.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text="Salary slip for John Doe Net Pay: 66500",
            manifest=sample_manifest,
            raw_file=b"bytes",
            filename="f.pdf",
        )

    assert res.provider == "local_ml"


@pytest.mark.asyncio
async def test_reconcile_evidence_disabled_falls_back_without_calling_client(
    sample_manifest, monkeypatch
):
    monkeypatch.setattr(settings, "SARVAM_DOCUMENT_ENABLED", False)
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")
    provider = SarvamProvider(client=SarvamClient(api_key="test-key"))

    with patch.object(
        provider.client, "create_extract_job", side_effect=AssertionError("must not be called")
    ):
        res = await provider.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text="text",
            manifest=sample_manifest,
            raw_file=b"bytes",
            filename="f.pdf",
        )

    assert res.provider == "local_ml"


@pytest.mark.asyncio
async def test_reconcile_evidence_master_switch_off_falls_back_without_calling_client(
    sample_manifest, monkeypatch
):
    """Regression guard: SARVAM_ENABLED is documented as a master kill-switch
    (backend/docs/sarvam_integration.md, .env.example) - it must be honored
    by reconcile_evidence itself, not just by the standalone voice/translate
    endpoints. Leaving SARVAM_DOCUMENT_ENABLED/SARVAM_API_KEY on their own
    is not enough to activate Sarvam if the master switch is off."""
    monkeypatch.setattr(settings, "SARVAM_ENABLED", False)
    monkeypatch.setattr(settings, "SARVAM_DOCUMENT_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")
    provider = SarvamProvider(client=SarvamClient(api_key="test-key"))

    with patch.object(
        provider.client, "create_extract_job", side_effect=AssertionError("must not be called")
    ):
        res = await provider.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text="text",
            manifest=sample_manifest,
            raw_file=b"bytes",
            filename="f.pdf",
        )

    assert res.provider == "local_ml"


@pytest.mark.asyncio
async def test_reconcile_evidence_unconfigured_key_falls_back(sample_manifest, monkeypatch):
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "")
    provider = SarvamProvider(client=SarvamClient(api_key=""))

    res = await provider.reconcile_evidence(
        doc_type="SALARY_SLIP",
        extracted_text="text",
        manifest=sample_manifest,
        raw_file=b"bytes",
        filename="f.pdf",
    )

    assert res.provider == "local_ml"


@pytest.mark.asyncio
async def test_reconcile_evidence_no_raw_file_falls_back(sample_manifest, monkeypatch):
    """Manual-details-entry path (no uploaded file) - Sarvam's vision model
    has nothing to look at, so it must fall back rather than error."""
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")
    provider = SarvamProvider(client=SarvamClient(api_key="test-key"))

    with patch.object(
        provider.client, "create_extract_job", side_effect=AssertionError("must not be called")
    ):
        res = await provider.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text='{"monthly_income": 66500}',
            manifest=sample_manifest,
            raw_file=None,
            filename=None,
        )

    assert res.provider == "local_ml"


@pytest.mark.asyncio
async def test_reconcile_evidence_no_extractable_content_is_not_verified(
    sample_manifest, monkeypatch
):
    """A real, completed job that found nothing readable (Sarvam's own
    no_extractable_content flag) must never be reported as verified with
    fabricated confidence - verified live: a genuinely unreadable scan
    still returns job status "completed", not "failed"."""
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")
    provider = SarvamProvider(client=SarvamClient(api_key="test-key"))

    post_resp = _mock_response({"job_id": "job-6", "status": "processing"})
    status_resp = _mock_response(
        {
            "job_id": "job-6",
            "status": "completed",
            "usage": {"pages_total": 1, "pages_succeeded": 1},
        }
    )
    download_url_resp = _mock_response({"url": "https://cdn.sarvam.ai/result.json"})
    result_resp = _mock_response(content=_zip_extraction({}, no_extractable_content=True))

    with (
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_resp)),
        patch(
            "httpx.AsyncClient.get",
            new=AsyncMock(side_effect=[status_resp, download_url_resp, result_resp]),
        ),
    ):
        res = await provider.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text="text",
            manifest=sample_manifest,
            raw_file=b"bytes",
            filename="f.pdf",
        )

    assert res.provider == "sarvam"
    assert res.verified is False
    assert res.confidence == 0.0
    assert res.detected == []


@pytest.mark.asyncio
async def test_reconcile_evidence_confidence_and_source_preserved_through_guardrails(
    sample_manifest, monkeypatch
):
    """The GuardrailedAIProvider wraps SarvamProvider without stripping the
    provider/confidence fields set on AIInterpretationResult."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "sarvam")
    monkeypatch.setattr(settings, "SARVAM_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "test-key")

    guarded = get_ai_provider(guardrailed=True)
    assert isinstance(guarded, GuardrailedAIProvider)
    sarvam_provider = guarded.inner
    assert isinstance(sarvam_provider, SarvamProvider)

    post_resp = _mock_response({"job_id": "job-5", "status": "processing"})
    status_resp = _mock_response(
        {
            "job_id": "job-5",
            "status": "completed",
            "usage": {"pages_total": 1, "pages_succeeded": 1},
        }
    )
    download_url_resp = _mock_response({"url": "https://cdn.sarvam.ai/result.json"})
    result_resp = _mock_response(
        content=_zip_extraction({"monthly_income": 72000}, {"monthly_income": 0.91})
    )

    with (
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=post_resp)),
        patch(
            "httpx.AsyncClient.get",
            new=AsyncMock(side_effect=[status_resp, download_url_resp, result_resp]),
        ),
    ):
        res = await guarded.reconcile_evidence(
            doc_type="SALARY_SLIP",
            extracted_text="Salary slip for John Doe Net Pay: 72000",
            manifest=sample_manifest,
            raw_file=b"bytes",
            filename="f.pdf",
        )

    assert res.provider == "sarvam"
    assert res.confidence == pytest.approx(0.91)
    assert res.raw_values.get("monthly_income") == 72000


def test_sarvam_client_never_logs_api_key(monkeypatch, caplog):
    """API key protection: constructing/using the client must never place
    the raw key into a log record."""
    client = SarvamClient(api_key="super-secret-key-value")
    headers = client._headers()
    assert headers["api-subscription-key"] == "super-secret-key-value"
    # No log call happens on header construction alone; this asserts the
    # invariant that _headers() itself performs no logging of the key.
    assert "super-secret-key-value" not in caplog.text


@pytest.mark.asyncio
async def test_sarvam_client_missing_api_key_raises_provider_error():
    client = SarvamClient(api_key="")
    with pytest.raises(SarvamProviderError):
        client._headers()


def test_extract_result_not_a_zip_raises_invalid_response_error():
    from app.ai.sarvam import _parse_extract_payload

    with pytest.raises(SarvamInvalidResponseError):
        _parse_extract_payload(b"not a zip file at all")


def test_extract_result_zip_with_malformed_json_raises_invalid_response_error():
    from app.ai.sarvam import _parse_extract_payload

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("extraction.json", "{not valid json")

    with pytest.raises(SarvamInvalidResponseError):
        _parse_extract_payload(buf.getvalue())


def test_extract_result_parses_real_verified_shape():
    """Direct unit test of the parser against the exact shape verified
    live against a real Sarvam account (see app/ai/sarvam.py's module
    docstring) - a ZIP containing extraction.json with data/
    field_confidence/field_sources/no_extractable_content."""
    from app.ai.sarvam import _parse_extract_payload

    raw = _zip_extraction({"monthly_income": 66500}, {"monthly_income": 1.0})
    extraction = _parse_extract_payload(raw)
    assert extraction.values == {"monthly_income": 66500}
    assert extraction.field_confidence == {"monthly_income": 1.0}
    assert extraction.no_extractable_content is False


def test_extract_result_no_extractable_content_flag_parsed():
    from app.ai.sarvam import _parse_extract_payload

    raw = _zip_extraction({}, no_extractable_content=True)
    extraction = _parse_extract_payload(raw)
    assert extraction.no_extractable_content is True
