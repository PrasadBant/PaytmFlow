"""Pure tests for app/core/review.py - no DB, no HTTP, matches
tests/unit/test_readiness.py's style."""

import pytest

from app.core.review import (
    ReviewCaseStatus,
    ReviewTransitionError,
    check_lock,
    validate_transition,
)


class TestValidTransitions:
    def test_review_required_to_under_review(self) -> None:
        validate_transition(ReviewCaseStatus.REVIEW_REQUIRED, ReviewCaseStatus.UNDER_REVIEW)

    def test_under_review_to_resolved(self) -> None:
        validate_transition(ReviewCaseStatus.UNDER_REVIEW, ReviewCaseStatus.RESOLVED)

    def test_under_review_to_additional_info_required(self) -> None:
        validate_transition(
            ReviewCaseStatus.UNDER_REVIEW, ReviewCaseStatus.ADDITIONAL_INFO_REQUIRED
        )

    def test_under_review_to_escalated(self) -> None:
        validate_transition(ReviewCaseStatus.UNDER_REVIEW, ReviewCaseStatus.ESCALATED)

    def test_additional_info_required_to_review_required(self) -> None:
        validate_transition(
            ReviewCaseStatus.ADDITIONAL_INFO_REQUIRED, ReviewCaseStatus.REVIEW_REQUIRED
        )

    def test_additional_info_required_to_under_review(self) -> None:
        validate_transition(
            ReviewCaseStatus.ADDITIONAL_INFO_REQUIRED, ReviewCaseStatus.UNDER_REVIEW
        )

    def test_additional_info_required_to_resolved(self) -> None:
        validate_transition(ReviewCaseStatus.ADDITIONAL_INFO_REQUIRED, ReviewCaseStatus.RESOLVED)

    def test_escalated_to_resolved(self) -> None:
        validate_transition(ReviewCaseStatus.ESCALATED, ReviewCaseStatus.RESOLVED)

    def test_any_open_status_to_cancelled(self) -> None:
        for status in (
            ReviewCaseStatus.REVIEW_REQUIRED,
            ReviewCaseStatus.UNDER_REVIEW,
            ReviewCaseStatus.ADDITIONAL_INFO_REQUIRED,
            ReviewCaseStatus.ESCALATED,
        ):
            validate_transition(status, ReviewCaseStatus.CANCELLED)


class TestInvalidTransitions:
    def test_resolved_is_terminal(self) -> None:
        for target in ReviewCaseStatus:
            if target == ReviewCaseStatus.RESOLVED:
                continue
            with pytest.raises(ReviewTransitionError):
                validate_transition(ReviewCaseStatus.RESOLVED, target)

    def test_cancelled_is_terminal(self) -> None:
        for target in ReviewCaseStatus:
            if target == ReviewCaseStatus.CANCELLED:
                continue
            with pytest.raises(ReviewTransitionError):
                validate_transition(ReviewCaseStatus.CANCELLED, target)

    def test_review_required_cannot_skip_to_resolved(self) -> None:
        with pytest.raises(ReviewTransitionError):
            validate_transition(ReviewCaseStatus.REVIEW_REQUIRED, ReviewCaseStatus.RESOLVED)

    def test_review_required_cannot_be_escalated_directly(self) -> None:
        with pytest.raises(ReviewTransitionError):
            validate_transition(ReviewCaseStatus.REVIEW_REQUIRED, ReviewCaseStatus.ESCALATED)

    def test_escalated_cannot_go_back_to_under_review(self) -> None:
        with pytest.raises(ReviewTransitionError):
            validate_transition(ReviewCaseStatus.ESCALATED, ReviewCaseStatus.UNDER_REVIEW)

    def test_double_resolve_is_invalid(self) -> None:
        """Guards against a double-click Submit Resolution creating a second
        mutation - the second call must be rejected as an invalid transition,
        never silently re-applied."""
        with pytest.raises(ReviewTransitionError):
            validate_transition(ReviewCaseStatus.RESOLVED, ReviewCaseStatus.RESOLVED)


class TestLockCheck:
    def test_unlocked_case_is_never_locked(self) -> None:
        result = check_lock(
            review_lock_until_is_future=False, assigned_reviewer="alice", requesting_reviewer="bob"
        )
        assert result.is_locked is False
        assert result.locked_by_other is False

    def test_locked_by_same_reviewer_is_not_locked_by_other(self) -> None:
        result = check_lock(
            review_lock_until_is_future=True, assigned_reviewer="alice", requesting_reviewer="alice"
        )
        assert result.is_locked is True
        assert result.locked_by_other is False

    def test_locked_by_different_reviewer_blocks(self) -> None:
        result = check_lock(
            review_lock_until_is_future=True, assigned_reviewer="alice", requesting_reviewer="bob"
        )
        assert result.is_locked is True
        assert result.locked_by_other is True

    def test_locked_future_with_no_assigned_reviewer_is_not_locked_by_other(self) -> None:
        result = check_lock(
            review_lock_until_is_future=True, assigned_reviewer=None, requesting_reviewer="bob"
        )
        assert result.is_locked is True
        assert result.locked_by_other is False


class TestLockTimezoneHandling:
    def test_to_utc_with_naive_and_aware(self) -> None:
        from datetime import UTC, datetime

        from app.services.review_service import _to_utc

        naive_dt = datetime(2026, 9, 19, 12, 0, 0)
        utc_dt = _to_utc(naive_dt)
        assert utc_dt.tzinfo == UTC
        assert utc_dt.hour == 12

        aware_dt = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)
        assert _to_utc(aware_dt) == aware_dt

    def test_is_locked_future_handles_sqlite_naive_and_postgres_aware(self) -> None:
        from datetime import UTC, datetime, timedelta
        from types import SimpleNamespace

        from app.services.review_service import _is_locked_future

        now_aware = datetime.now(UTC)

        # None lock
        case_none = SimpleNamespace(review_lock_until=None)
        assert _is_locked_future(case_none, now_aware) is False  # type: ignore[arg-type]

        # Naive future datetime (typical from SQLite DateTime column)
        future_naive = (datetime.now(UTC) + timedelta(minutes=15)).replace(tzinfo=None)
        case_future_naive = SimpleNamespace(review_lock_until=future_naive)
        assert _is_locked_future(case_future_naive, now_aware) is True  # type: ignore[arg-type]

        # Naive past datetime (expired lock from SQLite)
        past_naive = (datetime.now(UTC) - timedelta(minutes=5)).replace(tzinfo=None)
        case_past_naive = SimpleNamespace(review_lock_until=past_naive)
        assert _is_locked_future(case_past_naive, now_aware) is False  # type: ignore[arg-type]

        # Aware future datetime (typical from PostgreSQL TIMESTAMP WITH TIME ZONE)
        future_aware = datetime.now(UTC) + timedelta(minutes=15)
        case_future_aware = SimpleNamespace(review_lock_until=future_aware)
        assert _is_locked_future(case_future_aware, now_aware) is True  # type: ignore[arg-type]

        # Aware past datetime (expired lock from PostgreSQL)
        past_aware = datetime.now(UTC) - timedelta(minutes=5)
        case_past_aware = SimpleNamespace(review_lock_until=past_aware)
        assert _is_locked_future(case_past_aware, now_aware) is False  # type: ignore[arg-type]
