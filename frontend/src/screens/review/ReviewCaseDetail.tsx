import { useState } from 'react';
import type React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, AlertCircle, ShieldAlert, FileText, Lock } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { Spinner } from '@/components/primitives/Spinner';
import { Select } from '@/components/primitives/Select';
import { StatusBadge } from '@/components/StatusBadge';
import { JourneyDiff } from '@/components/JourneyDiff';
import { mapErrorToUxAction } from '@/api/errors';
import {
  useReviewCase,
  useReviewCaseAudit,
  useClaimCase,
  useResolveCase,
  useRequestInformation,
  useEscalateCase,
  type ReviewResolutionType,
} from '@/api/hooks/useReview';

const RESOLUTION_OPTIONS: { value: ReviewResolutionType; label: string }[] = [
  { value: 'EVIDENCE_SUFFICIENT', label: 'Evidence is sufficient' },
  { value: 'REQUEST_ADDITIONAL_INFORMATION', label: 'Request additional information' },
  { value: 'EVIDENCE_CANNOT_BE_VERIFIED', label: 'Evidence cannot be verified' },
  { value: 'CUSTOMER_INFO_NEEDS_CORRECTION', label: 'Customer information needs correction' },
  { value: 'ESCALATE_FOR_SPECIALIST_REVIEW', label: 'Escalate for specialist review' },
];

export const ReviewCaseDetail: React.FC = () => {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const { data: detail, isLoading, error, refetch } = useReviewCase(caseId);
  const { data: audit } = useReviewCaseAudit(caseId);

  const claimCase = useClaimCase();
  const resolveCase = useResolveCase();
  const requestInfo = useRequestInformation();
  const escalateCase = useEscalateCase();

  const [resolutionType, setResolutionType] = useState<ReviewResolutionType>('EVIDENCE_SUFFICIENT');
  const [reason, setReason] = useState('');
  const [notes, setNotes] = useState('');
  const [resolutionValue, setResolutionValue] = useState('');
  const [requestedDocsInput, setRequestedDocsInput] = useState('');
  const [customerMessage, setCustomerMessage] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div
        data-testid="review-case-detail-loading"
        className="min-h-[300px] flex items-center justify-center"
      >
        <Spinner size="lg" className="text-paytm-blue" />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-10">
        <div
          data-testid="review-case-detail-error"
          className="p-8 rounded-card bg-paytm-red-light border border-red-200 text-center space-y-4"
        >
          <AlertCircle className="w-10 h-10 text-paytm-red mx-auto" />
          <p className="text-sm text-content-secondary">
            {error ? mapErrorToUxAction(error).message : 'Case not found.'}
          </p>
          <Button variant="primary" onClick={() => refetch()}>
            Try Again
          </Button>
        </div>
      </div>
    );
  }

  const isTerminal = detail.status === 'RESOLVED' || detail.status === 'CANCELLED';
  const canAct = detail.status === 'UNDER_REVIEW' && !isTerminal;

  const handleClaim = (): void => {
    claimCase.mutate({ caseId: detail.case_id, expected_case_version: detail.case_version });
  };

  const handleSubmit = (): void => {
    setFormError(null);
    if (!reason.trim() && resolutionType !== 'REQUEST_ADDITIONAL_INFORMATION') {
      setFormError('A reason is required.');
      return;
    }

    if (resolutionType === 'REQUEST_ADDITIONAL_INFORMATION') {
      const docs = requestedDocsInput
        .split(',')
        .map((d) => d.trim())
        .filter(Boolean);
      if (docs.length === 0) {
        setFormError('List at least one requested document.');
        return;
      }
      if (!customerMessage.trim()) {
        setFormError('A customer-facing message is required.');
        return;
      }
      requestInfo.mutate({
        caseId: detail.case_id,
        requested_docs: docs,
        customer_message: customerMessage,
        expected_case_version: detail.case_version,
      });
      return;
    }

    if (resolutionType === 'ESCALATE_FOR_SPECIALIST_REVIEW') {
      escalateCase.mutate({
        caseId: detail.case_id,
        escalation_reason: reason,
        expected_case_version: detail.case_version,
      });
      return;
    }

    if (resolutionType === 'EVIDENCE_SUFFICIENT' && !resolutionValue.trim()) {
      setFormError('Confirm the value to use before marking evidence sufficient.');
      return;
    }

    resolveCase.mutate({
      caseId: detail.case_id,
      resolution_type: resolutionType,
      resolution_reason: reason,
      resolution_notes: notes || undefined,
      resolution_value:
        resolutionType === 'EVIDENCE_SUFFICIENT' && resolutionValue.trim()
          ? Number(resolutionValue) || resolutionValue
          : undefined,
      expected_case_version: detail.case_version,
    });
  };

  const mutationError =
    claimCase.error || resolveCase.error || requestInfo.error || escalateCase.error;
  const isSubmitting =
    claimCase.isPending || resolveCase.isPending || requestInfo.isPending || escalateCase.isPending;

  return (
    <div
      data-testid="review-case-detail"
      className="max-w-4xl mx-auto px-4 py-8 md:py-10 space-y-6"
    >
      <button
        onClick={() => navigate('/review/queue')}
        className="inline-flex items-center gap-1.5 text-sm text-content-secondary hover:text-content-primary"
      >
        <ArrowLeft className="w-4 h-4" /> Back to queue
      </button>

      {/* A. Case Header */}
      <Card padding="lg" className="bg-white border border-surface-border">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="text-xs font-mono text-content-tertiary">CASE {detail.case_number}</p>
            <h1 className="text-xl font-extrabold text-content-primary mt-1">
              {detail.reason_title}
            </h1>
            <p className="text-sm text-content-secondary mt-0.5">
              {detail.journey_display_name} Journey
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <StatusBadge status={detail.status} />
            {detail.is_locked && detail.assigned_reviewer && (
              <span className="inline-flex items-center gap-1 text-[11px] text-content-tertiary">
                <Lock className="w-3 h-3" /> {detail.assigned_reviewer}
              </span>
            )}
          </div>
        </div>
      </Card>

      {/* Why flagged */}
      <Card padding="lg" className="bg-white border border-surface-border space-y-2">
        <h2 className="text-sm font-bold text-content-primary flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-paytm-amber" /> Automation could not confidently
          resolve this case
        </h2>
        <p className="text-sm text-content-secondary">{detail.reason_description}</p>
        <p className="text-xs text-content-tertiary">Reason code: {detail.reason_code}</p>
      </Card>

      {/* AI Findings + Evidence Comparison */}
      <Card padding="lg" className="bg-white border border-surface-border space-y-3">
        <h2 className="text-sm font-bold text-content-primary">AI Findings</h2>
        <p className="text-xs text-content-tertiary">
          AI is advisory only. Final resolution requires human review.
        </p>
        {detail.evidence.length === 0 ? (
          <p className="text-sm text-content-secondary">No evidence documents on file yet.</p>
        ) : (
          <div className="grid sm:grid-cols-2 gap-3">
            {detail.evidence.map((e) => (
              <div
                key={e.evidence_id}
                data-testid={`evidence-${e.evidence_id}`}
                className="p-3 rounded-button border border-surface-border bg-surface-subtle/40 space-y-1"
              >
                <div className="flex items-center gap-2 text-xs font-semibold text-content-primary">
                  <FileText className="w-3.5 h-3.5" /> {e.doc_type}
                </div>
                <p className="text-xs text-content-tertiary truncate">{e.filename}</p>
                <p className="text-xs text-content-secondary">
                  {e.verified ? 'Classified & matched' : 'Not verified'}
                  {e.confidence != null ? ` · confidence ${e.confidence.toFixed(2)}` : ''}
                </p>
                {Object.entries(e.extracted_values ?? {}).map(([k, v]) => (
                  <p key={k} className="text-xs text-content-secondary">
                    {k}: <span className="font-semibold">{String(v)}</span>
                  </p>
                ))}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Journey Context */}
      <Card padding="lg" className="bg-white border border-surface-border space-y-3">
        <h2 className="text-sm font-bold text-content-primary">Customer Journey</h2>
        <div className="space-y-1.5">
          {detail.journey_context.fields.map((f) => (
            <div key={f.key} className="flex items-center justify-between gap-3 text-sm">
              <span className="text-content-secondary">{f.label}</span>
              <StatusBadge status={f.status} size="sm" />
            </div>
          ))}
        </div>
      </Card>

      {/* Journey Impact */}
      {detail.impact_preview && (
        <JourneyDiff diff={detail.impact_preview} variant="preview" />
      )}

      {/* Resolution */}
      <Card padding="lg" className="bg-white border border-surface-border space-y-4">
        <h2 className="text-sm font-bold text-content-primary">Resolve Evidence</h2>

        {!canAct && !isTerminal && (
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-content-secondary">Claim this case to act on it.</p>
            <Button variant="primary" onClick={handleClaim} isLoading={claimCase.isPending}>
              Claim Case
            </Button>
          </div>
        )}

        {isTerminal && (
          <p className="text-sm text-content-secondary" data-testid="case-terminal-message">
            This case is {detail.status.toLowerCase()}
            {detail.resolution_reason ? `: ${detail.resolution_reason}` : '.'}
          </p>
        )}

        {canAct && (
          <div className="space-y-3">
            <Select
              label="Resolution"
              required
              value={resolutionType}
              onChange={(e) => setResolutionType(e.target.value as ReviewResolutionType)}
              options={RESOLUTION_OPTIONS}
              data-testid="resolution-type-select"
            />

            {resolutionType === 'EVIDENCE_SUFFICIENT' && (
              <div>
                <label
                  htmlFor="resolution-value"
                  className="block text-xs font-semibold text-content-primary mb-1.5"
                >
                  Confirmed value
                </label>
                <input
                  id="resolution-value"
                  type="text"
                  value={resolutionValue}
                  onChange={(e) => setResolutionValue(e.target.value)}
                  data-testid="resolution-value-input"
                  className="w-full rounded-button bg-surface border border-surface-border px-3.5 py-2 text-sm"
                  placeholder="e.g. 50000"
                />
              </div>
            )}

            {resolutionType === 'REQUEST_ADDITIONAL_INFORMATION' ? (
              <>
                <div>
                  <label
                    htmlFor="requested-docs"
                    className="block text-xs font-semibold text-content-primary mb-1.5"
                  >
                    Requested documents (comma-separated)
                  </label>
                  <input
                    id="requested-docs"
                    type="text"
                    value={requestedDocsInput}
                    onChange={(e) => setRequestedDocsInput(e.target.value)}
                    data-testid="requested-docs-input"
                    className="w-full rounded-button bg-surface border border-surface-border px-3.5 py-2 text-sm"
                    placeholder="Latest salary slip, Bank statement"
                  />
                </div>
                <div>
                  <label
                    htmlFor="customer-message"
                    className="block text-xs font-semibold text-content-primary mb-1.5"
                  >
                    Message to customer
                  </label>
                  <textarea
                    id="customer-message"
                    value={customerMessage}
                    onChange={(e) => setCustomerMessage(e.target.value)}
                    data-testid="customer-message-input"
                    className="w-full rounded-button bg-surface border border-surface-border px-3.5 py-2 text-sm"
                    rows={2}
                  />
                </div>
              </>
            ) : (
              <div>
                <label
                  htmlFor="resolution-reason"
                  className="block text-xs font-semibold text-content-primary mb-1.5"
                >
                  {resolutionType === 'ESCALATE_FOR_SPECIALIST_REVIEW'
                    ? 'Escalation reason'
                    : 'Resolution reason'}
                </label>
                <textarea
                  id="resolution-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  data-testid="resolution-reason-input"
                  className="w-full rounded-button bg-surface border border-surface-border px-3.5 py-2 text-sm"
                  rows={2}
                  required
                />
              </div>
            )}

            {resolutionType !== 'REQUEST_ADDITIONAL_INFORMATION' &&
              resolutionType !== 'ESCALATE_FOR_SPECIALIST_REVIEW' && (
                <div>
                  <label
                    htmlFor="resolution-notes"
                    className="block text-xs font-semibold text-content-primary mb-1.5"
                  >
                    Notes (optional)
                  </label>
                  <textarea
                    id="resolution-notes"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    data-testid="resolution-notes-input"
                    className="w-full rounded-button bg-surface border border-surface-border px-3.5 py-2 text-sm"
                    rows={2}
                  />
                </div>
              )}

            {(formError || mutationError) && (
              <p className="text-xs text-paytm-red" data-testid="resolution-form-error">
                {formError || mapErrorToUxAction(mutationError!).message}
              </p>
            )}

            <Button
              variant="primary"
              onClick={handleSubmit}
              isLoading={isSubmitting}
              data-testid="submit-resolution-btn"
            >
              Submit Resolution
            </Button>
          </div>
        )}
      </Card>

      {/* Audit Trail */}
      {audit && audit.entries.length > 0 && (
        <Card padding="lg" className="bg-white border border-surface-border space-y-2">
          <h2 className="text-sm font-bold text-content-primary">Audit Timeline</h2>
          <ul className="space-y-1.5" data-testid="audit-timeline">
            {audit.entries.map((entry, idx) => (
              <li key={idx} className="text-xs text-content-secondary flex items-center gap-2">
                <span className="text-content-tertiary">
                  {new Date(entry.created_at).toLocaleTimeString()}
                </span>
                <span>{entry.event_type.replaceAll('_', ' ').toLowerCase()}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
};

export default ReviewCaseDetail;
