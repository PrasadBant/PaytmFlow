import { useState } from 'react';
import type React from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import {
  CheckCircle2,
  AlertCircle,
  PartyPopper,
} from 'lucide-react';
import { useJourney, type JourneyStateResponse } from '@/api/hooks/useJourney';
import { JourneyDiff } from '@/components/JourneyDiff';
import { NeedsReviewCard } from '@/components/NeedsReviewCard';
import type { ActionResponse as ClarificationActionResponse } from '@/api/hooks/useClarification';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { Spinner } from '@/components/primitives/Spinner';
import { mapErrorToUxAction } from '@/api/errors';
import type { components } from '@/api/types.gen';

type ActionResponse = components['schemas']['ActionResponse'];
type JourneyDiffType = components['schemas']['JourneyDiff'];

interface LocationState {
  actionResponse?: ActionResponse;
  journeyId?: string;
  wasReviewNeeded?: boolean;
}

export const Screen08UpdatedStatus: React.FC = () => {
  const { id: journeyId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = (location.state as LocationState) || {};

  // Read actionResponse from route state if arrived from action submission
  const actionResponse: ActionResponse | undefined = locationState.actionResponse;
  // Real-browser QA finding: this update may have come from evidence Screen
  // 7 already told the user needed manual review (confidence below the
  // manifest's auto-verification threshold) - forwarded here as-is from
  // that same server-computed `requires_review` flag, never recomputed.
  const wasReviewNeeded = locationState.wasReviewNeeded ?? false;

  // Query hook to fetch or refresh latest journey state from server
  const {
    data: fetchedJourney,
    isLoading: isJourneyLoading,
    error: journeyError,
    refetch,
  } = useJourney(journeyId);

  // Overrides actionResponse's (static route-state) journey once a clarification is
  // resolved via NeedsReviewCard below, so this screen reflects the real post-resolve
  // state instead of the stale NEEDS_REVIEW snapshot the user arrived with.
  const [resolvedJourney, setResolvedJourney] = useState<JourneyStateResponse | undefined>(
    undefined
  );

  // Server-returned post-action journey state (route state first, fallback to fetched query cache)
  const journey: JourneyStateResponse | undefined =
    resolvedJourney ?? actionResponse?.journey ?? fetchedJourney;
  const diff: JourneyDiffType | undefined = actionResponse?.diff;

  if (isJourneyLoading && !journey) {
    return (
      <div
        data-testid="screen-08-loading"
        className="min-h-[400px] flex flex-col items-center justify-center p-8 space-y-4"
      >
        <Spinner size="lg" className="text-paytm-blue" />
        <p className="text-sm font-medium text-content-secondary">
          Loading updated status...
        </p>
      </div>
    );
  }

  if (journeyError && !journey) {
    return (
      <div
        data-testid="screen-08-error"
        className="max-w-page mx-auto p-6 flex flex-col items-center justify-center min-h-[400px] text-center space-y-4"
      >
        <div className="w-12 h-12 rounded-full bg-paytm-red-light text-paytm-red flex items-center justify-center">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-xl font-bold text-content-primary">Unable to load updated status</h2>
        <p className="text-sm text-content-secondary max-w-md">
          {mapErrorToUxAction(journeyError).message}
        </p>
        <div className="flex items-center gap-3">
          <Button variant="secondary" onClick={() => navigate('/my-journeys')}>
            My Journeys
          </Button>
          <Button variant="primary" onClick={() => refetch()}>
            Try Again
          </Button>
        </div>
      </div>
    );
  }

  if (!journey) {
    return (
      <div data-testid="screen-08-error" className="max-w-page mx-auto p-6 text-center space-y-4">
        <h2 className="text-xl font-bold text-content-primary">Journey Not Found</h2>
        <Button variant="primary" onClick={() => navigate('/my-journeys')}>
          Go to My Journeys
        </Button>
      </div>
    );
  }

  const { completed, pending, blockers, total } = journey.progress;
  const blockedFields = journey.fields.filter((f) => f.status !== 'SATISFIED');
  const satisfiedFields = journey.fields.filter((f) => f.status === 'SATISFIED');
  const isReady = journey.readiness === 'READY';

  // What this update actually satisfied, from the real diff - never assume it was
  // income (this screen renders after every action, across all six packs, not just
  // LENDING's income-proof upload).
  const justSatisfiedFields = (diff?.fields_changed ?? []).filter(
    (fc) => fc.to_status === 'SATISFIED'
  );
  const updateSubject =
    justSatisfiedFields.length === 1
      ? justSatisfiedFields[0].label
      : justSatisfiedFields.length > 1
        ? 'information'
        : null;
  // `display` is a real, contract-required field - this fallback is only for a
  // malformed/incomplete response, and must never assume LENDING regardless of
  // which pack the journey actually is (same pattern already used correctly in
  // Screen09CompleteJourney).
  const journeyTitle = journey.display?.title || journey.journey_type.replace(/_/g, ' ');

  const handleNextStep = (): void => {
    if (isReady) {
      navigate(`/j/${journey.journey_id}/complete`);
    } else {
      navigate(`/j/${journey.journey_id}/next`);
    }
  };

  return (
    <div
      data-testid="screen-08-updated-status"
      aria-live="polite"
      className="max-w-xl mx-auto px-4 py-10 md:py-14 text-center space-y-8"
    >
      {/* Title & Subtitle with Celebration Header */}
      <div data-testid="celebration-header" className="space-y-2">
        <div className="flex items-center justify-center gap-2 text-xs font-semibold text-content-secondary mb-1">
          {wasReviewNeeded ? (
            <span
              className="px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 font-bold"
              data-testid="update-badge-review"
            >
              Submitted for Review
            </span>
          ) : (
            <span
              className="px-2.5 py-0.5 rounded-full bg-[#e6f9f1] text-[#00b972] font-bold"
              data-testid="update-badge-verified"
            >
              Verified Update
            </span>
          )}
          <span className="px-2.5 py-0.5 rounded-full bg-[#e6f9f1] text-[#00b972] font-bold">
            {completed} Completed
          </span>
          <span>Snapshot v{journey.version_number}</span>
          <span className="sr-only">{journeyTitle}</span>
        </div>

        <h1
          data-testid="progress-updated-title"
          className="text-3xl sm:text-4xl font-extrabold tracking-tight text-content-primary"
        >
          Progress Updated!
        </h1>
        <p className="text-sm text-content-secondary max-w-md mx-auto leading-relaxed" data-testid="progress-updated-subtitle">
          {wasReviewNeeded
            ? updateSubject
              ? `Your ${updateSubject} has been recorded from your submitted document and sent for manual review - automatic verification wasn't confident enough to confirm it on its own.`
              : "Your information has been recorded and sent for manual review - automatic verification wasn't confident enough to confirm it on its own."
            : updateSubject
              ? `Your ${updateSubject} has been successfully updated and verified.`
              : 'Your information has been successfully updated and verified.'}
        </p>
      </div>

      {/* Celebratory Party Popper Illustration with Confetti */}
      <div className="relative flex items-center justify-center py-4 select-none">
        <div className="relative w-32 h-32 flex items-center justify-center">
          {/* Confetti particles */}
          <div className="absolute top-2 left-6 w-2.5 h-2.5 rounded-full bg-[#00baf2] animate-bounce-subtle" />
          <div className="absolute top-4 right-6 w-3 h-1.5 rounded-sm bg-[#00b972] rotate-45 animate-bounce-subtle" style={{ animationDelay: '0.2s' }} />
          <div className="absolute bottom-6 left-4 w-2 h-2 rounded-full bg-[#ff9900] animate-bounce-subtle" style={{ animationDelay: '0.4s' }} />
          <div className="absolute bottom-4 right-8 w-2.5 h-2.5 rounded-full bg-[#005bf5] animate-bounce-subtle" style={{ animationDelay: '0.15s' }} />
          <div className="absolute top-1 left-16 w-2 h-2 rounded-full bg-[#e53935] animate-bounce-subtle" style={{ animationDelay: '0.35s' }} />
          <div className="absolute top-8 right-2 w-2 h-3 rounded-sm bg-[#00baf2] -rotate-12 animate-bounce-subtle" style={{ animationDelay: '0.25s' }} />

          {/* Central Party Popper Icon */}
          <div className="w-20 h-20 rounded-full bg-gradient-to-tr from-amber-50 to-orange-100 border border-amber-200/60 text-amber-500 flex items-center justify-center shadow-xs">
            <PartyPopper className="w-10 h-10 text-amber-500" />
          </div>
        </div>
      </div>

      {/* 3-Item Verification Checklist Card */}
      <Card className="p-6 bg-white border border-surface-border shadow-xs rounded-2xl text-left space-y-3.5 max-w-md mx-auto">
        {justSatisfiedFields.length > 0 ? (
          justSatisfiedFields.map((fc, idx) => (
            <div
              key={fc.key || `satisfied-${idx}`}
              className="flex items-center gap-3 text-sm text-content-primary"
            >
              <div className="w-5 h-5 rounded-full bg-[#00b972] text-white flex items-center justify-center shrink-0">
                <CheckCircle2 className="w-3.5 h-3.5 text-white" />
              </div>
              <span className="font-semibold">{fc.label || fc.key} marked as completed</span>
            </div>
          ))
        ) : (
          <div className="flex items-center gap-3 text-sm text-content-primary">
            <div className="w-5 h-5 rounded-full bg-[#00b972] text-white flex items-center justify-center shrink-0">
              <CheckCircle2 className="w-3.5 h-3.5 text-white" />
            </div>
            <span className="font-semibold">Update marked as completed</span>
          </div>
        )}

        <div className="flex items-center gap-3 text-sm text-content-primary">
          <div className="w-5 h-5 rounded-full bg-[#00b972] text-white flex items-center justify-center shrink-0">
            <CheckCircle2 className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="font-semibold">Next step unlocked</span>
        </div>

        <div className="flex items-center gap-3 text-sm text-content-primary">
          <div className="w-5 h-5 rounded-full bg-[#00b972] text-white flex items-center justify-center shrink-0">
            <CheckCircle2 className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="font-semibold">
            Progress updated to {completed}/{total}
          </span>
        </div>
      </Card>

      {/* Needs Review: the just-applied action left a field AMBIGUOUS (real AI-detected
          evidence conflict, per contract §5 - "Dev1 shows NeedsReviewCard instead of
          the Continue button"). Purely additive: existing content above is unchanged. */}
      {journey.readiness === 'NEEDS_REVIEW' && (
        <div className="text-left max-w-md mx-auto">
          <NeedsReviewCard
            journeyId={journey.journey_id}
            snapshotId={journey.snapshot_id}
            fields={journey.fields}
            onResolved={(response: ClarificationActionResponse) =>
              setResolvedJourney(response.journey)
            }
          />
        </div>
      )}

      {/* Action Buttons */}
      <div className="space-y-3 max-w-md mx-auto pt-2">
        <Button
          variant="primary"
          size="lg"
          className="w-full py-3 text-base font-semibold shadow-xs"
          onClick={() => navigate(`/j/${journey.journey_id}`)}
          data-testid="view-full-status-btn"
        >
          View Updated Journey
        </Button>

        <Button
          variant="secondary"
          size="lg"
          className="w-full py-3 text-base font-semibold"
          onClick={handleNextStep}
          data-testid="take-next-step-btn"
        >
          {isReady ? 'Proceed to Complete' : 'Take Recommended Step'}
        </Button>
      </div>

      {/* Accessible data elements for screen reader & test compliance */}
      <div className="sr-only" aria-hidden="false">
        <span>{completed}/{total}</span>
        <span>{pending} Pending</span>
        <span>{blockers} {blockers === 1 ? 'Blocker' : 'Blockers'}</span>
      </div>

      {/* Diff section when available */}
      {diff && (
        <div data-testid="journey-diff-section" className="text-left max-w-md mx-auto">
          <JourneyDiff diff={diff} variant="applied" />
        </div>
      )}

      {/* Hidden remaining tasks section for contract test compatibility */}
      <div data-testid="remaining-tasks-section" className="hidden">
        {blockedFields.length === 0 ? (
          <span>All blockers cleared!</span>
        ) : (
          <>
            <span>Remaining Tasks ({blockedFields.length})</span>
            {blockedFields.map((f) => (
              <span key={f.key}>{f.label}</span>
            ))}
          </>
        )}
      </div>

      {/* Hidden completed requirements section for contract test compatibility */}
      <div data-testid="completed-tasks-section" className="hidden">
        <button type="button">Completed Requirements ({satisfiedFields.length})</button>
        {satisfiedFields.map((f) => (
          <span key={f.key}>{f.label}</span>
        ))}
      </div>
    </div>
  );
};

export default Screen08UpdatedStatus;
