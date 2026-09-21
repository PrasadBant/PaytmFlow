"""Unit tests for the chat API route's diff-lookup guard - the boot/chat
performance requirement is that Journey Diff is only ever fetched via the
existing JourneyService.get_diff (never re-derived), and only when a prior
version genuinely exists.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.chat import _get_diff_if_available
from app.schemas.enums import FieldStatus, JourneyStatus, Readiness
from app.schemas.journeys import (
    DisplayInfo,
    FieldChange,
    JourneyDiff,
    JourneyStateResponse,
    ProgressCounts,
    ReadinessDiff,
)


def _journey_state(version_number: int) -> JourneyStateResponse:
    return JourneyStateResponse(
        journey_id=uuid4(),
        journey_type="LENDING",
        schema_version="1.0.0",
        snapshot_id=uuid4(),
        version_number=version_number,
        readiness=Readiness.NEEDS_REVIEW,
        status=JourneyStatus.NEEDS_REVIEW,
        fields=[],
        progress=ProgressCounts(completed=3, pending=1, blockers=0, total=5),
        display=DisplayInfo(title="Personal Loan", summary="₹5,00,000 · Home Renovation"),
    )


def _diff() -> JourneyDiff:
    return JourneyDiff(
        from_version=1,
        to_version=2,
        fields_changed=[
            FieldChange(
                key="monthly_income",
                label="Monthly Income",
                from_status=FieldStatus.SATISFIED,
                to_status=FieldStatus.AMBIGUOUS,
            )
        ],
        actions_unlocked=[],
        actions_removed=[],
        readiness=ReadinessDiff(**{"from": Readiness.NOT_READY, "to": Readiness.NEEDS_REVIEW}),
    )


@pytest.mark.asyncio
async def test_get_diff_if_available_returns_none_below_version_two():
    """A journey still on its first snapshot has nothing to diff - this must
    be recognized WITHOUT calling JourneyService.get_diff at all (no wasted
    query, no spurious 404 from the service layer)."""
    journey = MagicMock(id=uuid4())
    journey_state = _journey_state(version_number=1)
    db = MagicMock()

    with patch("app.api.v1.chat.JourneyService.get_diff", new=AsyncMock()) as mock_get_diff:
        result = await _get_diff_if_available(journey=journey, journey_state=journey_state, db=db)

    assert result is None
    mock_get_diff.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_diff_if_available_fetches_real_diff_when_version_available():
    """From version_number 2 onward, the actual diff between the previous
    and current snapshot is fetched via the existing JourneyService.get_diff
    - never a second/duplicate diff engine."""
    journey = MagicMock(id=uuid4())
    journey_state = _journey_state(version_number=2)
    expected_diff = _diff()
    db = MagicMock()

    with patch(
        "app.api.v1.chat.JourneyService.get_diff", new=AsyncMock(return_value=expected_diff)
    ) as mock_get_diff:
        result = await _get_diff_if_available(journey=journey, journey_state=journey_state, db=db)

    assert result is expected_diff
    mock_get_diff.assert_awaited_once_with(journey=journey, from_ver=1, to_ver=2, db=db)


@pytest.mark.asyncio
async def test_get_diff_if_available_degrades_gracefully_on_lookup_failure():
    """A defensive-only path (e.g. a snapshot somehow missing): the chat
    request must still succeed with diff=None rather than failing the whole
    reply over an advisory extra."""
    journey = MagicMock(id=uuid4())
    journey_state = _journey_state(version_number=3)
    db = MagicMock()
    failure = HTTPException(status_code=404, detail="not found")

    with patch("app.api.v1.chat.JourneyService.get_diff", new=AsyncMock(side_effect=failure)):
        result = await _get_diff_if_available(journey=journey, journey_state=journey_state, db=db)

    assert result is None
