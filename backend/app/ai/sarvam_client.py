"""Thin async HTTP client for Sarvam AI's REST API.

Endpoints below are verified against the live Sarvam API documentation
(https://docs.sarvam.ai, checked while building this integration) - nothing
here is an invented/guessed endpoint:

- Document AI Extract (schema-based structured extraction):
    POST /doc-ai/v1/job/extract
- Document AI Digitise (OCR + layout):
    POST /doc-ai/v1/job/digitise
- Job status (terminal: completed | partially_completed | failed | rejected):
    GET  /doc-ai/v1/job/{job_id}/status
- Job result download URL:
    GET  /doc-ai/v1/job/{job_id}/download-url
- Speech-to-text (Saaras, synchronous - no job lifecycle):
    POST /speech-to-text
- Translation (Mayura):
    POST /translate
- Chat completions (OpenAI-compatible shape):
    POST /chat/completions

Auth: `api-subscription-key` header. This client never logs the API key,
raw document bytes, or raw audio bytes - only operation name, status code,
and duration (backend/CLAUDE.md: "Never log AI keys, cookie values, or file
contents").
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class SarvamError(Exception):
    """Base class for all Sarvam client errors."""


class SarvamTimeoutError(SarvamError):
    """The request to Sarvam did not complete within the configured timeout."""


class SarvamRateLimitError(SarvamError):
    """Sarvam responded 429 - caller should fall back, not retry immediately."""


class SarvamProviderError(SarvamError):
    """Sarvam is unreachable, returned a 5xx, or the client is misconfigured."""


class SarvamInvalidResponseError(SarvamError):
    """Sarvam returned a 4xx, non-JSON, or unexpectedly-shaped response."""


@dataclass
class SarvamJobHandle:
    job_id: str
    status: str
    run_id: str | None = None


@dataclass
class SarvamJobStatus:
    job_id: str
    status: str
    pipeline: str | None = None
    pages_total: int | None = None
    pages_processed: int | None = None
    pages_succeeded: int | None = None
    pages_failed: int | None = None


TERMINAL_JOB_STATUSES = {"completed", "partially_completed", "failed", "rejected"}
SUCCESSFUL_JOB_STATUSES = {"completed", "partially_completed"}


class SarvamClient:
    """Stateless per-call async client - one short-lived httpx.AsyncClient per
    request, matching the existing LLMProvider._call_llm pattern in
    app/ai/llm.py, so tests can mock `httpx.AsyncClient.post`/`.get` the same
    way tests/unit/test_ai_llm.py already does."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.SARVAM_API_KEY
        self.base_url = (base_url or settings.SARVAM_BASE_URL).rstrip("/")
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(settings.SARVAM_TIMEOUT_SECONDS)
        )

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        if not self.api_key:
            raise SarvamProviderError("SARVAM_API_KEY is not configured")
        headers = {"api-subscription-key": self.api_key}
        if extra:
            headers.update(extra)
        return headers

    def _raise_for_status(self, response: httpx.Response, operation: str) -> None:
        if response.status_code == 429:
            raise SarvamRateLimitError(f"Sarvam rate limit exceeded during {operation}")
        if response.status_code >= 500:
            raise SarvamProviderError(
                f"Sarvam server error ({response.status_code}) during {operation}"
            )
        if response.status_code >= 400:
            raise SarvamInvalidResponseError(
                f"Sarvam rejected the request ({response.status_code}) during {operation}"
            )

    def _parse_json(self, response: httpx.Response, operation: str) -> dict[str, Any]:
        try:
            return response.json()
        except ValueError as exc:
            raise SarvamInvalidResponseError(
                f"Sarvam returned non-JSON during {operation}"
            ) from exc

    async def _post(
        self,
        path: str,
        *,
        headers: dict[str, str],
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        operation: str,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    url, headers=headers, files=files, data=data, json=json_body
                )
        except httpx.TimeoutException as exc:
            raise SarvamTimeoutError(f"Sarvam request timed out during {operation}") from exc
        except httpx.HTTPError as exc:
            raise SarvamProviderError(f"Sarvam request failed during {operation}: {exc}") from exc

        logger.info("sarvam_api_call", operation=operation, status_code=response.status_code)
        self._raise_for_status(response, operation)
        return self._parse_json(response, operation)

    async def _get(self, path: str, *, headers: dict[str, str], operation: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            raise SarvamTimeoutError(f"Sarvam request timed out during {operation}") from exc
        except httpx.HTTPError as exc:
            raise SarvamProviderError(f"Sarvam request failed during {operation}: {exc}") from exc

        logger.info("sarvam_api_call", operation=operation, status_code=response.status_code)
        self._raise_for_status(response, operation)
        return self._parse_json(response, operation)

    # ---- Document AI -----------------------------------------------------

    async def create_extract_job(
        self,
        file_bytes: bytes,
        filename: str,
        schema: dict[str, Any],
        language: str = "en-IN",
    ) -> SarvamJobHandle:
        headers = self._headers()
        files = {"file": (filename, file_bytes)}
        data = {"schema": _json.dumps(schema), "language": language, "output_format": "json"}
        result = await self._post(
            "/doc-ai/v1/job/extract",
            headers=headers,
            files=files,
            data=data,
            operation="create_extract_job",
        )
        job_id = result.get("job_id")
        if not job_id:
            raise SarvamInvalidResponseError("Sarvam extract-job response missing 'job_id'")
        return SarvamJobHandle(
            job_id=job_id, status=result.get("status", "created"), run_id=result.get("run_id")
        )

    async def create_digitise_job(
        self,
        file_bytes: bytes,
        filename: str,
        language: str = "en-IN",
        output_format: str = "json",
    ) -> SarvamJobHandle:
        headers = self._headers()
        files = {"file": (filename, file_bytes)}
        data = {"language": language, "output_format": output_format}
        result = await self._post(
            "/doc-ai/v1/job/digitise",
            headers=headers,
            files=files,
            data=data,
            operation="create_digitise_job",
        )
        job_id = result.get("job_id")
        if not job_id:
            raise SarvamInvalidResponseError("Sarvam digitise-job response missing 'job_id'")
        return SarvamJobHandle(
            job_id=job_id, status=result.get("status", "created"), run_id=result.get("run_id")
        )

    async def poll_job_status(self, job_id: str) -> SarvamJobStatus:
        headers = self._headers()
        result = await self._get(
            f"/doc-ai/v1/job/{job_id}/status", headers=headers, operation="poll_job_status"
        )
        usage = result.get("usage") or {}
        return SarvamJobStatus(
            job_id=result.get("job_id", job_id),
            status=result.get("status", "unknown"),
            pipeline=result.get("pipeline"),
            pages_total=usage.get("pages_total"),
            pages_processed=usage.get("pages_processed"),
            pages_succeeded=usage.get("pages_succeeded"),
            pages_failed=usage.get("pages_failed"),
        )

    async def get_download_url(self, job_id: str) -> str:
        headers = self._headers()
        result = await self._get(
            f"/doc-ai/v1/job/{job_id}/download-url", headers=headers, operation="get_download_url"
        )
        url = result.get("url")
        if not url:
            raise SarvamInvalidResponseError("Sarvam download-url response missing 'url'")
        return url

    async def download_result(self, url: str) -> bytes:
        """Downloads the job's result payload from the pre-signed URL returned
        by get_download_url(). Not routed through _get()/_headers(): a
        pre-signed URL carries its own auth and must NOT also receive the
        api-subscription-key header."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url)
        except httpx.TimeoutException as exc:
            raise SarvamTimeoutError("Timed out downloading Sarvam job result") from exc
        except httpx.HTTPError as exc:
            raise SarvamProviderError(f"Failed downloading Sarvam job result: {exc}") from exc
        self._raise_for_status(response, "download_result")
        return response.content

    # ---- Speech / Translate / Chat ---------------------------------------

    async def speech_to_text(
        self,
        audio_bytes: bytes,
        filename: str,
        language_code: str = "unknown",
        model: str | None = None,
    ) -> dict[str, Any]:
        headers = self._headers()
        files = {"file": (filename, audio_bytes)}
        data = {"model": model or settings.SARVAM_STT_MODEL, "language_code": language_code}
        return await self._post(
            "/speech-to-text", headers=headers, files=files, data=data, operation="speech_to_text"
        )

    async def translate(
        self,
        text: str,
        target_language_code: str,
        source_language_code: str = "auto",
    ) -> dict[str, Any]:
        headers = self._headers(extra={"Content-Type": "application/json"})
        body = {
            "input": text,
            "source_language_code": source_language_code,
            "target_language_code": target_language_code,
        }
        return await self._post(
            "/translate", headers=headers, json_body=body, operation="translate"
        )

    async def chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str = "sarvam-m",
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str:
        headers = self._headers(extra={"Content-Type": "application/json"})
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        result = await self._post(
            "/chat/completions", headers=headers, json_body=body, operation="chat_completion"
        )
        try:
            return str(result["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise SarvamInvalidResponseError(
                "Sarvam chat completion response missing expected fields"
            ) from exc
