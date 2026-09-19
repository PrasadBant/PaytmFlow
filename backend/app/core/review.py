"""Pure state-machine rules for Human Review / Exception Resolution cases.

No DB/AI/API/services/evidence imports (enforced by .importlinter's
`core-is-pure` contract) - this module only decides whether a requested
review-case status transition is legal, mirroring how
`app/core/deterministic_check.py` is the sole authority for journey-action
legality. The impure orchestration (row locks, persistence, audit writes,
re-entering the journey mutation chain) lives in
`app/services/review_service.py`.
"""

from dataclasses import dataclass
from enum import StrEnum


class ReviewCaseStatus(StrEnum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ADDITIONAL_INFO_REQUIRED = "ADDITIONAL_INFO_REQUIRED"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


ALLOWED_TRANSITIONS: dict[ReviewCaseStatus, set[ReviewCaseStatus]] = {
    ReviewCaseStatus.REVIEW_REQUIRED: {
        ReviewCaseStatus.UNDER_REVIEW,
        ReviewCaseStatus.CANCELLED,
    },
    ReviewCaseStatus.UNDER_REVIEW: {
        ReviewCaseStatus.UNDER_REVIEW,
        ReviewCaseStatus.RESOLVED,
        ReviewCaseStatus.ADDITIONAL_INFO_REQUIRED,
        ReviewCaseStatus.ESCALATED,
        ReviewCaseStatus.CANCELLED,
    },
    ReviewCaseStatus.ADDITIONAL_INFO_REQUIRED: {
        # A case does not auto-transition when the customer submits new
        # evidence (evidence upload is independent of this record) - the
        # reviewer manually reclaims (-> UNDER_REVIEW) or resolves directly
        # once they see the new evidence in the case detail.
        ReviewCaseStatus.REVIEW_REQUIRED,
        ReviewCaseStatus.UNDER_REVIEW,
        ReviewCaseStatus.RESOLVED,
        ReviewCaseStatus.CANCELLED,
    },
    ReviewCaseStatus.ESCALATED: {
        ReviewCaseStatus.RESOLVED,
        ReviewCaseStatus.CANCELLED,
    },
    ReviewCaseStatus.RESOLVED: set(),
    ReviewCaseStatus.CANCELLED: set(),
}


class ReviewTransitionError(Exception):
    """Raised when a requested review-case status transition is not legal."""

    def __init__(self, current: ReviewCaseStatus, requested: ReviewCaseStatus):
        super().__init__(
            f"Cannot transition review case from '{current.value}' to '{requested.value}'"
        )
        self.current = current
        self.requested = requested


@dataclass(frozen=True)
class ReviewLockCheck:
    is_locked: bool
    locked_by_other: bool


def validate_transition(current: ReviewCaseStatus, requested: ReviewCaseStatus) -> None:
    """Raises ReviewTransitionError if `current -> requested` is not an allowed edge."""
    if requested not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ReviewTransitionError(current, requested)


def check_lock(
    review_lock_until_is_future: bool,
    assigned_reviewer: str | None,
    requesting_reviewer: str,
) -> ReviewLockCheck:
    """Pure lock-ownership check: is the case locked, and if so, by someone else?

    `review_lock_until_is_future` is computed by the impure caller (needs
    `datetime.now()`) and passed in as a plain bool so this function stays
    deterministic and time-free.
    """
    if not review_lock_until_is_future:
        return ReviewLockCheck(is_locked=False, locked_by_other=False)
    locked_by_other = assigned_reviewer is not None and assigned_reviewer != requesting_reviewer
    return ReviewLockCheck(is_locked=True, locked_by_other=locked_by_other)
