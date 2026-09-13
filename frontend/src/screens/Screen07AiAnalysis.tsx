import { useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { ArrowLeft, AlertCircle, CheckCircle2, Sparkles } from 'lucide-react';
import { useJourney } from '@/api/hooks/useJourney';
import { useApplyAction } from '@/api/hooks/useApplyAction';
import { EvidenceCard } from '@/components/EvidenceCard';
import { ConsequencePreview } from '@/components/ConsequencePreview';
import { JourneyDiff } from '@/components/JourneyDiff';
import { Button } from '@/components/primitives/Button';
import { Card } from '@/components/primitives/Card';
import { Spinner } from '@/components/primitives/Spinner';
import { mapErrorToUxAction } from '@/api/errors';
import type { components } from '@/api/types.gen';

type EvidenceResponse = components['schemas']['EvidenceResponse'];

interface LocationState {
  evidenceResponse?: EvidenceResponse;
  journeyId?: string;
  actionId?: string;
  snapshotId?: string;
}

function generateIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export const Screen07AiAnalysis: React.FC = () => {
  const { id: journeyId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = (location.state as LocationState) || {};

  const [applyError, setApplyError] = useState<string | null>(null);

  const {
    data: journey,
    isLoading: isJourneyLoading,
    error: journeyError,
  } = useJourney(journeyId);

  const applyAction = useApplyAction();

  const evidenceResponse: EvidenceResponse | undefined = locationState.evidenceResponse;
  const snapshotId = locationState.snapshotId || journey?.snapshot_id || '';
  // Never fabricate an action_id: it must come from the action the user actually
  // navigated here to resolve (locationState.actionId, forwarded by Screen 6) or
  // from what THIS document's own analysis proposes. If neither is present -
  // e.g. a stale deep link, or a document that didn't match any pending
  // requirement - there is no correct action to apply, and handleApply below
  // refuses to submit rather than guessing a different pack's action.
  const actionId = locationState.actionId || evidenceResponse?.proposed_action_id || '';

  // A real AI-detected conflict (EvidenceConflict.ambiguity_id, from the evidence
  // response itself) is forwarded on apply so the mutation can genuinely flag the
  // targeted field AMBIGUOUS instead of silently marking it satisfied. `input` is a
  // free-form object per the contract - no schema change.
  const conflictAmbiguityId = evidenceResponse?.interpretation.conflicts?.[0]?.ambiguity_id;

  const handleApply = async (): Promise<void> => {
    if (!journeyId || !snapshotId || !evidenceResponse || applyAction.isPending) return;
    if (!actionId) {
      setApplyError('We could not determine which requirement this document resolves. Please go back and re-select the action.');
      return;
    }
    setApplyError(null);

    try {
      const response = await applyAction.mutateAsync({
        journeyId,
        action_id: actionId,
        expected_snapshot_id: snapshotId,
        idempotency_key: generateIdempotencyKey(),
        input: {
          evidence_id: evidenceResponse.evidence_id,
          ...(conflictAmbiguityId ? { ambiguity_id: conflictAmbiguityId } : {}),
        },
      });

      navigate(`/j/${journeyId}/updated`, {
        state: {
          actionResponse: response,
          journeyId,
        },
      });
    } catch (err) {
      setApplyError(mapErrorToUxAction(err).message);
    }
  };

  if (isJourneyLoading && !evidenceResponse) {
    return (
      <div
        data-testid="screen-07-loading"
        className="min-h-[400px] flex flex-col items-center justify-center p-8 space-y-4"
      >
        <Spinner size="lg" className="text-paytm-blue" />
        <p className="text-sm font-medium text-content-secondary">
          Loading analysis...
        </p>
      </div>
    );
  }

  if (journeyError && !evidenceResponse) {
    return (
      <div
        data-testid="screen-07-error"
        className="max-w-page mx-auto p-6 flex flex-col items-center justify-center min-h-[400px] text-center space-y-4"
      >
        <div className="w-12 h-12 rounded-full bg-paytm-red-light text-paytm-red flex items-center justify-center">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-xl font-bold text-content-primary">Unable to load analysis</h2>
        <p className="text-sm text-content-secondary max-w-md">
          {mapErrorToUxAction(journeyError).message}
        </p>
        <Button variant="secondary" onClick={() => navigate(`/j/${journeyId}/next`)}>
          Return to Recommendation
        </Button>
      </div>
    );
  }

  // If page was reached directly without evidenceResponse state, render informative fallback
  if (!evidenceResponse) {
    return (
      <div data-testid="screen-07-ai-analysis" className="max-w-3xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate(`/j/${journeyId}/next`)}
          className="text-content-secondary hover:text-content-primary -ml-2 mb-2 inline-flex items-center gap-1.5"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Recommendation</span>
        </Button>

        <Card className="p-8 text-center space-y-4 border border-surface-border">
          <div className="w-12 h-12 rounded-full bg-paytm-blue-50 text-paytm-blue flex items-center justify-center mx-auto">
            <Sparkles className="w-6 h-6" />
          </div>
          <h2 className="text-xl font-bold text-content-primary">No Evidence Upload to Analyze</h2>
          <p className="text-sm text-content-secondary max-w-md mx-auto">
            Please select an action from your recommendations and upload the required document or enter details.
          </p>
          <Button variant="primary" onClick={() => navigate(`/j/${journeyId}/next`)}>
            View Recommendations
          </Button>
        </Card>
      </div>
    );
  }

  const {
    filename,
    uploaded_at,
    size_bytes,
    interpretation,
    consequence_preview,
    diff_preview,
    requires_review,
  } = evidenceResponse;

  return (
    <div data-testid="screen-07-ai-analysis" className="max-w-3xl mx-auto px-4 py-8 md:py-10 space-y-6">
      {/* Top Header */}
      <div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate(`/j/${journeyId}/next`)}
          className="text-paytm-blue hover:text-paytm-blue-action -ml-2 mb-2 inline-flex items-center gap-1.5 font-semibold text-sm"
          data-testid="back-to-rec-btn"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back</span>
        </Button>

        <h1 className="text-2xl sm:text-3xl font-bold text-content-primary tracking-tight">
          AI Analysis
          <span className="sr-only">AI Document Analysis & Preview</span>
        </h1>
        <p className="text-sm text-content-secondary mt-1">
          We&apos;ve analyzed your document and here&apos;s what it means.
        </p>
      </div>

      {/* 1. Evidence Document Card */}
      <EvidenceCard
        filename={filename || 'Uploaded document'}
        uploadedAt={uploaded_at}
        sizeBytes={size_bytes}
        verified={interpretation.verified}
        requiresReview={requires_review}
        detected={interpretation.detected}
      />

      {/* 2. Green Insight Card matching reference */}
      <Card
        data-testid="ai-summary-card"
        className="p-4 bg-[#e6f9f1] border border-[#00b972]/30 rounded-card flex items-start gap-3 text-content-primary"
      >
        <div className="w-6 h-6 rounded-full bg-[#00b972] text-white flex items-center justify-center shrink-0 mt-0.5">
          <CheckCircle2 className="w-4 h-4 text-white" aria-hidden="true" />
        </div>
        <div className="space-y-0.5 min-w-0">
          <h3 className="text-sm font-bold text-content-primary">
            This document looks good!
          </h3>
          <p className="text-xs text-content-secondary leading-relaxed" data-testid="ai-summary-text">
            {interpretation.summary || 'Based on this, your verification criteria are satisfied.'}
          </p>
        </div>
      </Card>

      {/* 3. Deterministic Expected Outcome Preview */}
      <ConsequencePreview preview={consequence_preview} />

      {/* 4. State Diff Preview (if provided) */}
      {diff_preview && <JourneyDiff diff={diff_preview} variant="preview" />}

      {/* 5. Error Alert (if apply mutation fails) */}
      {applyError && (
        <div
          data-testid="apply-error-banner"
          className="p-4 rounded-card bg-paytm-red-light border border-paytm-red/20 flex items-start gap-3 text-paytm-red"
        >
          <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
          <div className="text-sm font-medium">{applyError}</div>
        </div>
      )}

      {/* 6. Footer Actions */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-surface-border">
        <Button
          type="button"
          variant="secondary"
          onClick={() => navigate(`/j/${journeyId}/next`)}
          disabled={applyAction.isPending}
          className="w-full sm:w-auto px-6 py-2.5"
        >
          Back
        </Button>

        {requires_review ? (
          <div className="flex flex-col items-stretch sm:items-end gap-3 w-full sm:w-auto">
            <div
              data-testid="requires-review-notice"
              className="flex items-center gap-2 text-xs text-amber-700 bg-amber-50 p-2.5 rounded-card border border-amber-200"
            >
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>This evidence requires manual review or clarification before continuing.</span>
            </div>
            <Button
              type="button"
              variant="primary"
              onClick={handleApply}
              disabled={applyAction.isPending}
              data-testid="submit-for-review-btn"
              className="w-full sm:w-auto px-8 py-2.5 inline-flex items-center justify-center gap-2"
            >
              {applyAction.isPending ? (
                <>
                  <Spinner size="sm" className="mr-2" />
                  <span>Processing...</span>
                </>
              ) : (
                <span>Submit for Review →</span>
              )}
            </Button>
          </div>
        ) : (
          <Button
            type="button"
            variant="primary"
            onClick={handleApply}
            disabled={applyAction.isPending}
            data-testid="continue-apply-btn"
            className="w-full sm:w-auto px-8 py-2.5 inline-flex items-center justify-center gap-2"
          >
            {applyAction.isPending ? (
              <>
                <Spinner size="sm" className="mr-2" />
                <span>Processing...</span>
              </>
            ) : (
              <span>Continue →</span>
            )}
          </Button>
        )}
      </div>
    </div>
  );
};

export default Screen07AiAnalysis;
