import { useEffect, useState, type ReactElement } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, AlertCircle } from 'lucide-react';
import { useRecommendation, type ActionOption } from '@/api/hooks/useRecommendation';
import { useJourney } from '@/api/hooks/useJourney';
import { RecommendationCard } from '@/components/RecommendationCard';
import { ActionList } from '@/components/ActionList';
import { AssistantHelpCard } from '@/components/AssistantHelpCard';
import { DeadEndState } from '@/components/DeadEndState';
import { FormActionModal } from '@/components/FormActionModal';
import type { ActionResponse } from '@/api/hooks/useApplyAction';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { Spinner } from '@/components/primitives/Spinner';

export function Screen05Recommendation(): ReactElement {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const {
    data: recData,
    isLoading: isRecLoading,
    error: recError,
    refetch: refetchRec,
  } = useRecommendation(id);

  const {
    isLoading: isJourneyLoading,
  } = useJourney(id);

  const isLoading = isRecLoading || isJourneyLoading;

  // FORM-kind actions render inline as "a generic action modal rendered from
  // input_schema" per contract (kind tells Dev1 which UI to open: EVIDENCE -> Screen 6,
  // FORM -> generic action modal, CLARIFICATION -> NeedsReviewCard). Screen 5 already
  // holds the full ActionOption (incl. input_schema) for both the recommendation and
  // its alternatives, so it can open the modal directly instead of navigating away.
  const [formModalAction, setFormModalAction] = useState<ActionOption | null>(null);

  // Auto-redirect if journey readiness is already READY (Contract rule: READY -> Screen 9)
  useEffect(() => {
    if (recData && recData.readiness === 'READY') {
      navigate(`/j/${id}/complete`, { replace: true });
    }
  }, [recData, id, navigate]);

  if (isLoading) {
    return (
      <div data-testid="screen-05-loading" className="flex flex-col items-center justify-center min-h-[50vh] p-8">
        <Spinner size="lg" className="text-paytm-blue mb-4" />
        <p className="text-sm font-medium text-content-secondary">Analyzing next best action...</p>
      </div>
    );
  }

  if (recData && recData.readiness === 'DEAD_END') {
    return <DeadEndState journeyId={id} />;
  }

  if (recError || !recData) {
    return (
      <div data-testid="screen-05-error" className="max-w-page mx-auto p-6 md:p-8">
        <Link
          to={`/j/${id}`}
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-paytm-blue hover:text-paytm-navy mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Current Status
        </Link>
        <Card className="p-8 text-center max-w-lg mx-auto">
          <AlertCircle className="w-10 h-10 text-paytm-red mx-auto mb-3" />
          <h2 className="text-lg font-bold text-content-primary mb-2">Unable to Load Recommendation</h2>
          <p className="text-sm text-content-secondary mb-6">
            Failed to evaluate optimal next actions for this journey.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Button variant="secondary" onClick={() => navigate(`/j/${id}`)}>
              Back to Status
            </Button>
            <Button variant="primary" onClick={() => refetchRec()}>
              Try Again
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const heading = 'Recommended Next Step';
  const subtext = 'Based on your application data, this is the best next action to move forward.';

  const handleActionSelect = (action: ActionOption): void => {
    // CLARIFICATION-kind actions are a targeted ambiguity question, not something to
    // "open" - per contract, kind tells Dev1 which UI to use: EVIDENCE -> Screen 6,
    // FORM -> generic action modal, CLARIFICATION -> NeedsReviewCard. Screen 6 has no
    // upload/form UI for a clarification (there is nothing to upload and no
    // input_schema to fill), so route back to Screen 4 instead, which renders
    // NeedsReviewCard for any AMBIGUOUS field.
    if (action.kind === 'CLARIFICATION') {
      navigate(`/j/${id}`);
      return;
    }
    if (action.kind === 'FORM') {
      setFormModalAction(action);
      return;
    }
    navigate(`/j/${id}/act/${action.action_id}`);
  };

  const handleFormActionSuccess = (response: ActionResponse): void => {
    navigate(`/j/${id}/updated`, {
      state: { actionResponse: response, journeyId: id },
    });
  };

  return (
    <div data-testid="screen-05-recommendation" className="max-w-4xl mx-auto px-4 py-8 md:py-10 space-y-6">
      {/* Back Link */}
      <div>
        <Link
          to={`/j/${id}`}
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

      {/* Main layout: Recommendation + Alternatives + Assistant Card */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          {recData.recommendation ? (
            <RecommendationCard
              action={recData.recommendation}
              onSelect={handleActionSelect}
              source={recData.source}
            />
          ) : (
            <Card className="p-6 text-center text-content-secondary">
              <p className="font-semibold text-content-primary">No pending actions required.</p>
              <p className="text-xs mt-1">Review your status or proceed to completion.</p>
            </Card>
          )}

          {recData.alternatives && recData.alternatives.length > 0 && (
            <ActionList
              alternatives={recData.alternatives}
              onSelect={handleActionSelect}
            />
          )}
        </div>

        {/* Sidebar Assistant Guidance */}
        <div className="space-y-6">
          <AssistantHelpCard />
        </div>
      </div>

      <FormActionModal
        isOpen={formModalAction !== null}
        onClose={() => setFormModalAction(null)}
        action={formModalAction}
        journeyId={id || ''}
        expectedSnapshotId={recData.snapshot_id}
        onSuccess={handleFormActionSuccess}
      />
    </div>
  );
}

export default Screen05Recommendation;
