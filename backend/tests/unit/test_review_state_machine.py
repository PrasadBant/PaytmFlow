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
