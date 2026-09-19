import { useState, type ReactElement } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { AlertCircle, ArrowRight, ArrowLeft, CheckCircle2, ChevronDown, ChevronUp } from 'lucide-react';
import { useJourney } from '@/api/hooks/useJourney';
import { ProgressRing } from '@/components/ProgressRing';
import { BlockerCard } from '@/components/BlockerCard';
import { NeedsReviewCard } from '@/components/NeedsReviewCard';
import { ReviewStatusCard } from '@/components/ReviewStatusCard';
import { StatusBadge } from '@/components/StatusBadge';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { Spinner } from '@/components/primitives/Spinner';

export function Screen04CurrentStatus(): ReactElement {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: journey, isLoading, error, refetch } = useJourney(id);
  const [showSatisfied, setShowSatisfied] = useState(false);

  if (isLoading) {
    return (
      <div data-testid="screen-04-loading" className="flex flex-col items-center justify-center min-h-[50vh] p-8">
        <Spinner size="lg" className="text-paytm-blue mb-4" />
        <p className="text-sm font-medium text-content-secondary">Loading journey status...</p>
      </div>
    );
  }

  if (error || !journey) {
    return (
      <div data-testid="screen-04-error" className="max-w-page mx-auto p-6 md:p-8">
        <Card className="p-8 text-center max-w-lg mx-auto">
          <AlertCircle className="w-10 h-10 text-paytm-red mx-auto mb-3" />
          <h2 className="text-lg font-bold text-content-primary mb-2">Unable to Load Status</h2>
          <p className="text-sm text-content-secondary mb-6">
            The requested journey details could not be retrieved.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Button variant="secondary" onClick={() => navigate('/my-journeys')}>
              My Journeys
            </Button>
            <Button variant="primary" onClick={() => refetch()}>
              Try Again
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const heading = 'Your Current Status';
  const subtext = "We've analyzed your application and found a few items that need your attention.";

  // AMBIGUOUS fields need a targeted clarification question, not the generic
  // "navigate to the original resolve action" flow BlockerCard offers - split them
  // out so NeedsReviewCard (the real §5.1 Needs-Review UI) handles them instead.
  // This is also the screen `resume_screen: NEEDS_REVIEW` sends the applicant back
  // to, so it must work standalone, not only right after the action that caused it.
  const ambiguousFields = journey.fields.filter((f) => f.status === 'AMBIGUOUS');
  
  const rawBlockedFields = journey.fields.filter(
    (f) => f.status !== 'SATISFIED' && f.status !== 'AMBIGUOUS'
  );

  // Error #6: Overlapping/incorrect blockers
  // Group fields by resolve_action_id so we don't render duplicate blocker panels
  // for multiple fields that are resolved by the exact same action.
  const blockedFieldsMap = new Map<string, typeof rawBlockedFields[0]>();
  const blockedFields: typeof rawBlockedFields = [];
  
  for (const field of rawBlockedFields) {
    if (field.resolve_action_id) {
      if (!blockedFieldsMap.has(field.resolve_action_id)) {
        blockedFieldsMap.set(field.resolve_action_id, field);
        blockedFields.push(field);
      } else {
        // If we already have a blocker for this action, optionally we could
        // merge the labels/explanations, but usually the primary field is sufficient.
        // We'll just skip adding a duplicate panel.
      }
    } else {
      blockedFields.push(field); // Fields without a resolve_action_id aren't grouped
    }
  }

  const satisfiedFields = journey.fields.filter((f) => f.status === 'SATISFIED');

  const { completed, pending, blockers, total } = journey.progress;

  const handleResolve = (actionId: string): void => {
    navigate(`/j/${journey.journey_id}/act/${actionId}`, {
      state: { snapshotId: journey.snapshot_id },
    });
  };

  return (
    <div
      data-testid="screen-04-current-status"
      aria-live="polite"
      className="max-w-3xl mx-auto px-4 py-8 md:py-10 space-y-6"
    >
      {/* Top Back Link */}
      <div>
        <Link
          to="/start"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-paytm-blue hover:text-paytm-blue-action transition-colors group"
        >
          <ArrowLeft className="w-4 h-4 transition-transform group-hover:-translate-x-1" />
          Back
        </Link>
      </div>

      {/* Header section */}
      <div>
        <h1 className="text-2xl md:text-3xl font-bold text-content-primary tracking-tight">
          {heading}
        </h1>
        <p className="mt-1.5 text-sm text-content-secondary leading-relaxed">
          {subtext}
        </p>
      </div>

      {/* Progress & Legend Card */}
      <Card className="p-6 md:p-8 bg-surface shadow-card border-surface-border">
        <div className="flex flex-col sm:flex-row items-center justify-around gap-6 md:gap-10">
          {/* Progress Ring */}
          <div className="flex flex-col items-center">
            <ProgressRing completed={completed} total={total} size="lg" />
          </div>

          {/* Legend */}
          <div className="flex flex-col gap-3.5 min-w-[200px]">
            <div className="flex items-center gap-3">
              <span className="w-4 h-4 rounded-full bg-paytm-green shrink-0" aria-hidden="true" />
              <span className="text-sm font-semibold text-content-primary">{completed} Completed</span>
            </div>

            <div className="flex items-center gap-3">
              <span className="w-4 h-4 rounded-full bg-slate-300 shrink-0" aria-hidden="true" />
              <span className="text-sm font-semibold text-content-secondary">{pending} Pending</span>
            </div>

            <div className="flex items-center gap-3">
              <span
                className="w-4 h-4 rounded-full bg-paytm-red shrink-0 flex items-center justify-center text-[9px] font-bold text-white leading-none"
                aria-hidden="true"
              >
                !
              </span>
              <span className="text-sm font-semibold text-content-primary">{blockers} {blockers === 1 ? 'Blocker' : 'Blockers'}</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Needs Review: at least one field has a real AI-detected conflict awaiting
          a targeted clarification. Shown here (not just right after the action that
          caused it) so a resumed or freshly-navigated-to journey still surfaces it -
          this is exactly the screen resume_screen: NEEDS_REVIEW points back to. */}
      {ambiguousFields.length > 0 && (
        <NeedsReviewCard
          journeyId={journey.journey_id}
          snapshotId={journey.snapshot_id}
          fields={ambiguousFields}
          onResolved={() => refetch()}
        />
      )}

      {/* Human Review case status - a durable, reviewer-tracked exception
          record (see backend review_cases table), distinct from the
          in-flight ambiguity NeedsReviewCard resolves directly. */}
      <ReviewStatusCard journeyId={journey.journey_id} />

      {/* Blocked Items Section */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 sm:gap-4">
          <h2 className="text-lg font-bold text-content-primary tracking-tight">
            Blocked Items ({blockedFields.length})
          </h2>
          <span className="text-xs text-content-secondary">
            Resolve blockers to progress your journey
          </span>
        </div>

        {blockedFields.length === 0 ? (
          <Card className="p-6 text-center text-content-secondary">
            <CheckCircle2 className="w-8 h-8 text-paytm-green mx-auto mb-2" />
            <p className="font-semibold text-content-primary">No blockers remaining!</p>
            <p className="text-xs mt-1">All initial requirements have been satisfied.</p>
          </Card>
        ) : (
          <div className="space-y-3">
            {blockedFields.map((field) => (
              <BlockerCard
                key={field.key}
                field={field}
                onResolve={handleResolve}
              />
            ))}
          </div>
        )}
      </div>

      {/* Satisfied Requirements (Collapsible) */}
      {satisfiedFields.length > 0 && (
        <div className="pt-2 border-t border-surface-border">
          <button
            type="button"
            onClick={() => setShowSatisfied(!showSatisfied)}
            className="flex items-center justify-between w-full py-3 text-left group text-sm font-semibold text-content-secondary hover:text-content-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-paytm-cyan rounded-button"
            aria-expanded={showSatisfied}
          >
            <span className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-paytm-green" />
              <span>Completed Requirements ({satisfiedFields.length})</span>
            </span>
            {showSatisfied ? (
              <ChevronUp className="w-4 h-4 text-content-secondary" />
            ) : (
              <ChevronDown className="w-4 h-4 text-content-secondary" />
            )}
          </button>

          {showSatisfied && (
            <div className="mt-3 space-y-2">
              {satisfiedFields.map((field) => (
                <div
                  key={field.key}
                  className="p-3.5 rounded-card bg-surface-subtle border border-surface-border flex items-center justify-between gap-3 text-xs"
                >
                  <div>
                    <p className="font-semibold text-content-primary">{field.label}</p>
                    {field.display_value && (
                      <p className="text-content-secondary mt-0.5">{field.display_value}</p>
                    )}
                  </div>
                  <StatusBadge status="SATISFIED" size="sm" />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Footer / Continue CTA */}
      <div className="pt-4 flex justify-end">
        <Button
          variant="primary"
          size="lg"
          className="w-full sm:w-auto"
          onClick={() => navigate(`/j/${journey.journey_id}/next`)}
        >
          <span>Take Recommended Step</span>
          <span className="sr-only"> — Recommended Next Step</span>
          <ArrowRight className="w-4 h-4 ml-2" />
        </Button>
      </div>
    </div>
  );
}

export default Screen04CurrentStatus;
