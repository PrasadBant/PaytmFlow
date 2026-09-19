import { useState } from 'react';
import type React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  AlertCircle,
  Lock,
  CheckCircle2,
  Hourglass,
  ArrowUpCircle,
  Clock,
  HelpCircle,
  Eye,
} from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { Spinner } from '@/components/primitives/Spinner';
import { Select } from '@/components/primitives/Select';
import { StatusBadge } from '@/components/StatusBadge';
import { mapErrorToUxAction } from '@/api/errors';
import { formatRelativeTime } from '@/lib/utils';
import {
  useReviewCase,
  useReviewCaseAudit,
  useClaimCase,
  useResolveCase,
  useRequestInformation,
  useEscalateCase,
  type ReviewResolutionType,
} from '@/api/hooks/useReview';
import { WhySeeingCase } from './components/WhySeeingCase';
import { EvidenceComparisonWorkspace } from './components/EvidenceComparisonWorkspace';
import { AiEvidenceSummary } from './components/AiEvidenceSummary';
import { JourneyContextWorkspace } from './components/JourneyContextWorkspace';
import { CustomerHandoffLoop } from './components/CustomerHandoffLoop';
import { AuditTimelineWorkspace } from './components/AuditTimelineWorkspace';
import { ReviewActionModal } from './components/ReviewActionModal';

const RESOLUTION_OPTIONS: { value: ReviewResolutionType; label: string; description: string }[] = [
  {
    value: 'EVIDENCE_SUFFICIENT',
    label: 'Resolve Evidence (Sufficient)',
    description: 'Evidence verifies customer declaration. Confirmed value will update journey.',
  },
  {
    value: 'CUSTOMER_INFO_NEEDS_CORRECTION',
    label: 'Customer Information Needs Correction',
    description: 'Evidence contradicts customer declaration. Customer must correct their inputs.',
  },
  {
    value: 'EVIDENCE_CANNOT_BE_VERIFIED',
    label: 'Evidence Cannot Be Verified',
    description: 'Submitted document is unreadable, invalid, or cannot be verified.',
  },
  {
    value: 'REQUEST_ADDITIONAL_INFORMATION',
    label: 'Request Additional Information',
    description: 'Ask customer for alternate or additional supporting documents.',
  },
  {
    value: 'ESCALATE_FOR_SPECIALIST_REVIEW',
    label: 'Escalate to Specialist',
    description: 'Route to senior specialist queue for policy exception or legal review.',
  },
];

const QUICK_DOC_TAGS = [
  'Latest 3-Month Salary Slip',
  'Bank Statement (PDF)',
  'Form 16 / ITR Acknowledgement',
  'Identity Proof (Aadhaar / PAN)',
  'Cancelled Cheque',
];

const ESCALATION_CATEGORIES = [
  { value: 'Evidence Ambiguity', label: 'Evidence Ambiguity (Conflicting/Unclear Documents)' },
  { value: 'Policy/Rule Ambiguity', label: 'Policy/Rule Ambiguity (Underwriting Edge Case)' },
  { value: 'Technical/Extraction Issue', label: 'Technical/Extraction Issue (OCR Failure)' },
  { value: 'Data Inconsistency', label: 'Data Inconsistency (Bureau vs Customer Mismatch)' },
  { value: 'Other', label: 'Other Operational Exception' },
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

  // Resolution Form States
  const [resolutionType, setResolutionType] = useState<ReviewResolutionType>('EVIDENCE_SUFFICIENT');
  const [reason, setReason] = useState('');
  const [notes, setNotes] = useState('');
  const [resolutionValue, setResolutionValue] = useState('');

  // Request Information States
  const [requestedDocsInput, setRequestedDocsInput] = useState('');
  const [customerMessage, setCustomerMessage] = useState('');

  // Escalation States
  const [escalationCategory, setEscalationCategory] = useState(ESCALATION_CATEGORIES[0].value);

  // Modal & Validation
  const [showConfirm, setShowConfirm] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div
        data-testid="review-case-detail-loading"
        className="min-h-[350px] flex items-center justify-center bg-white rounded-card border border-surface-border my-8 max-w-5xl mx-auto"
      >
        <Spinner size="lg" className="text-paytm-blue" />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12">
        <div
          data-testid="review-case-detail-error"
          className="p-8 rounded-card bg-paytm-red-light border border-red-200 text-center space-y-4 shadow-xs"
        >
          <AlertCircle className="w-10 h-10 text-paytm-red mx-auto" />
          <h2 className="text-base font-bold text-content-primary">Unable to load review case</h2>
          <p className="text-sm text-content-secondary">
            {error ? mapErrorToUxAction(error).message : 'Case record could not be found.'}
          </p>
          <div className="flex items-center justify-center gap-3 pt-2">
            <Button variant="outline" onClick={() => navigate('/review/queue')}>
              Back to Queue
            </Button>
            <Button variant="primary" onClick={() => refetch()}>
              Try Again
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const isTerminal = detail.status === 'RESOLVED' || detail.status === 'CANCELLED';
  const isClaimedByMe = detail.status === 'UNDER_REVIEW';
  const isAwaitingCustomer = detail.status === 'ADDITIONAL_INFO_REQUIRED';
  const isEscalated = detail.status === 'ESCALATED';

  const canAct = isClaimedByMe && !isTerminal;

  const handleClaim = (): void => {
    claimCase.mutate({
      caseId: detail.case_id,
      expected_case_version: detail.case_version,
    });
  };

  const handlePreSubmit = (): void => {
    setFormError(null);

    if (resolutionType === 'REQUEST_ADDITIONAL_INFORMATION') {
      const docs = requestedDocsInput.split(',').map((d) => d.trim()).filter(Boolean);
      if (docs.length === 0) {
        setFormError('List at least one requested document.');
        return;
      }
      if (!customerMessage.trim()) {
        setFormError('A customer-facing message is required.');
        return;
      }
    } else if (resolutionType === 'ESCALATE_FOR_SPECIALIST_REVIEW') {
      if (!reason.trim()) {
        setFormError('An escalation reason is required for specialist handoff.');
        return;
      }
    } else {
      if (!reason.trim()) {
        setFormError('A reason is required before resolving.');
        return;
      }
      if (resolutionType === 'EVIDENCE_SUFFICIENT' && !resolutionValue.trim()) {
        setFormError('Confirm the value to use before marking evidence sufficient.');
        return;
      }
    }

    setShowConfirm(true);
  };

  const executeResolution = (): void => {
    setShowConfirm(false);

    if (resolutionType === 'REQUEST_ADDITIONAL_INFORMATION') {
      const docs = requestedDocsInput.split(',').map((d) => d.trim()).filter(Boolean);
      requestInfo.mutate({
        caseId: detail.case_id,
        requested_docs: docs,
        customer_message: customerMessage,
        expected_case_version: detail.case_version,
      });
      return;
    }

    if (resolutionType === 'ESCALATE_FOR_SPECIALIST_REVIEW') {
      const fullReason = `[${escalationCategory}] ${reason}${notes ? ` | Notes: ${notes}` : ''}`;
      escalateCase.mutate({
        caseId: detail.case_id,
        escalation_reason: fullReason,
        expected_case_version: detail.case_version,
      });
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

  const addDocTag = (tag: string) => {
    const currentTags = requestedDocsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
    if (!currentTags.includes(tag)) {
      setRequestedDocsInput(currentTags.length > 0 ? `${currentTags.join(', ')}, ${tag}` : tag);
    }
  };

  const mutationError =
    claimCase.error || resolveCase.error || requestInfo.error || escalateCase.error;
  const isSubmitting =
    claimCase.isPending || resolveCase.isPending || requestInfo.isPending || escalateCase.isPending;

  const docsArray = requestedDocsInput
    .split(',')
    .map((d) => d.trim())
    .filter(Boolean);

  return (
    <div data-testid="review-case-detail" className="max-w-7xl mx-auto px-4 py-8 md:py-10 space-y-6">
      {/* Top Navigation & Breadcrumb */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate('/review/queue')}
          className="inline-flex items-center gap-1.5 text-xs font-bold text-paytm-blue-action hover:text-paytm-blue transition-colors group"
        >
          <ArrowLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
          <span>Return to Review Queue</span>
        </button>

        <span className="text-xs text-content-tertiary font-mono">
          Case Version v{detail.case_version}
        </span>
      </div>

      {/* Case Header Workspace */}
      <Card padding="lg" className="bg-white border border-surface-border shadow-xs space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="text-xs font-mono font-bold text-content-primary bg-slate-100 px-2 py-0.5 rounded-sm border border-slate-200">
                {detail.case_number}
              </span>

              <span
                className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full ${
                  detail.priority === 'HIGH'
                    ? 'bg-red-50 text-red-700 border border-red-200/60'
                    : detail.priority === 'MEDIUM'
                    ? 'bg-amber-50 text-amber-800 border border-amber-200/60'
                    : 'bg-slate-100 text-slate-700'
                }`}
              >
                {detail.priority} Priority
              </span>

              <span className="text-xs font-semibold text-content-secondary">
                {detail.journey_display_name} Journey
              </span>

              <span className="text-xs text-content-tertiary">&middot;</span>

              <span className="text-xs text-content-tertiary font-mono">
                Field: {detail.field_key}
              </span>
            </div>

            <h1 className="text-xl sm:text-2xl font-extrabold text-content-primary tracking-tight">
              {detail.reason_title}
            </h1>

            <div className="flex items-center gap-4 text-xs text-content-tertiary flex-wrap">
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" /> Opened {formatRelativeTime(detail.created_at)}
              </span>
              <span>Updated {formatRelativeTime(detail.updated_at)}</span>
              {detail.resolved_at && (
                <span className="text-emerald-700 font-semibold">
                  Resolved {formatRelativeTime(detail.resolved_at)}
                </span>
              )}
            </div>
          </div>

          {/* Right Status & Header Primary Action */}
          <div className="flex flex-col sm:flex-row lg:flex-col items-start lg:items-end gap-3 shrink-0 pt-2 lg:pt-0 border-t lg:border-t-0 border-surface-border">
            <div className="flex items-center gap-2">
              <StatusBadge status={detail.status} />
              {detail.is_locked && detail.assigned_reviewer && (
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-700 bg-indigo-50 px-2 py-1 rounded-md border border-indigo-200/60">
                  <Lock className="w-3.5 h-3.5" /> Claimed by {detail.assigned_reviewer}
                </span>
              )}
            </div>

            {/* State-aware CTA in header */}
            {!canAct && !isTerminal && (
              <Button
                variant="primary"
                size="sm"
                onClick={handleClaim}
                isLoading={claimCase.isPending}
                className="whitespace-nowrap text-xs"
              >
                Start Review
              </Button>
            )}

            {canAct && (
              <span className="text-xs font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200 flex items-center gap-1">
                <Eye className="w-3.5 h-3.5" /> Active Review Mode
              </span>
            )}
          </div>
        </div>
      </Card>

      {/* Customer ↔ Reviewer Handoff Lifecycle */}
      <CustomerHandoffLoop status={detail.status} />

      {/* Main Workspace Layout (2 Columns) */}
      <div className="grid lg:grid-cols-3 gap-6 items-start">
        {/* Left Column (2 Cols): Investigation & Resolution */}
        <div className="lg:col-span-2 space-y-6">
          {/* 1. Why Seeing This Case? Hero */}
          <WhySeeingCase detail={detail} />

          {/* 2. Evidence Comparison & Extraction */}
          <EvidenceComparisonWorkspace detail={detail} />

          {/* 2b. AI Evidence Summary (advisory only) */}
          <AiEvidenceSummary caseId={detail.case_id} />

          {/* 3. Resolution & Action Panel */}
          <Card padding="lg" className="bg-white border-2 border-slate-200 shadow-sm space-y-5">
            <div className="border-b border-surface-border pb-3 flex items-center justify-between">
              <div>
                <h2 className="text-base font-extrabold text-content-primary">
                  Exception Resolution
                </h2>
                <p className="text-xs text-content-secondary">
                  Execute deterministic recovery, request missing evidence, or escalate.
                </p>
              </div>

              <span className="text-[10px] font-mono text-content-tertiary uppercase">
                Optimistic Lock v{detail.case_version}
              </span>
            </div>

            {/* UNCLAIMED STATE: Must claim first */}
            {!canAct && !isTerminal && !isAwaitingCustomer && (
              <div className="bg-indigo-50/60 p-5 rounded-card border border-indigo-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-indigo-950">
                    Claim this case to act on it.
                  </h3>
                  <p className="text-xs text-indigo-800">
                    Locking the case prevents other reviewers from overwriting your decision concurrently.
                  </p>
                </div>
                <Button
                  variant="primary"
                  onClick={handleClaim}
                  isLoading={claimCase.isPending}
                  className="whitespace-nowrap shrink-0"
                >
                  Claim Case
                </Button>
              </div>
            )}

            {/* WAITING CUSTOMER STATE: Handoff boundary */}
            {isAwaitingCustomer && (
              <div className="bg-amber-50/60 p-5 rounded-card border border-amber-200 space-y-4">
                <div className="flex items-start gap-3">
                  <Hourglass className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <h3 className="text-sm font-bold text-amber-950">
                      Waiting on Customer Response
                    </h3>
                    <p className="text-xs text-amber-900">
                      Additional information was requested from the customer. The journey is paused until new documents are submitted.
                    </p>
                  </div>
                </div>

                {detail.requested_information && (
                  <div className="bg-white p-3.5 rounded-button border border-amber-200/80 space-y-2 text-xs">
                    {detail.requested_information.requested_docs && (
                      <p className="font-semibold text-content-primary">
                        Requested: <span className="font-bold text-amber-900">{detail.requested_information.requested_docs.join(', ')}</span>
                      </p>
                    )}
                    {detail.requested_information.customer_message && (
                      <p className="text-content-secondary italic">
                        &ldquo;{detail.requested_information.customer_message}&rdquo;
                      </p>
                    )}
                  </div>
                )}

                <div className="pt-1 flex items-center gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleClaim}
                    isLoading={claimCase.isPending}
                    className="text-xs"
                  >
                    Resume / Reclaim Case
                  </Button>
                </div>
              </div>
            )}

            {/* ESCALATED STATE */}
            {isEscalated && (
              <div className="bg-red-50/50 p-5 rounded-card border border-red-200 space-y-3">
                <div className="flex items-center gap-2">
                  <ArrowUpCircle className="w-5 h-5 text-red-700" />
                  <h3 className="text-sm font-bold text-red-950">
                    Case Escalated to Specialist
                  </h3>
                </div>
                <div className="bg-white p-3.5 rounded-button border border-red-200 text-xs text-content-primary leading-relaxed">
                  {detail.escalation_reason || 'Escalated for senior review.'}
                </div>
                <p className="text-[11px] text-content-tertiary">
                  Case is handled in the underwriting exception pool.
                </p>
              </div>
            )}

            {/* TERMINAL RESOLVED STATE */}
            {isTerminal && (
              <div className="bg-emerald-50/50 p-5 rounded-card border border-emerald-200 space-y-3">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-700" />
                  <h3 className="text-sm font-bold text-emerald-950">
                    Case is {detail.status.toLowerCase()}
                  </h3>
                </div>

                <div className="bg-white p-3.5 rounded-button border border-emerald-200 text-xs space-y-1.5">
                  <p className="font-bold text-content-primary">
                    Resolution: <span className="text-emerald-800">{detail.resolution_type?.replace(/_/g, ' ')}</span>
                  </p>
                  {detail.resolution_reason && (
                    <p className="text-content-secondary">
                      Reason: {detail.resolution_reason}
                    </p>
                  )}
                  {detail.resolution_notes && (
                    <p className="text-content-tertiary italic">
                      Notes: {detail.resolution_notes}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* ACTIVE WORKSPACE: Form is enabled */}
            {canAct && (
              <div className="space-y-5">
                {/* Resolution Type Picker */}
                <div className="space-y-1.5">
                  <Select
                    label="Select Operational Action"
                    required
                    value={resolutionType}
                    onChange={(e) => setResolutionType(e.target.value as ReviewResolutionType)}
                    options={RESOLUTION_OPTIONS.map((o) => ({
                      value: o.value,
                      label: o.label,
                    }))}
                    data-testid="resolution-type-select"
                  />
                  <p className="text-[11px] text-content-tertiary">
                    {RESOLUTION_OPTIONS.find((o) => o.value === resolutionType)?.description}
                  </p>
                </div>

                {/* Sub-Form: EVIDENCE_SUFFICIENT */}
                {resolutionType === 'EVIDENCE_SUFFICIENT' && (
                  <div className="bg-blue-50/40 p-4 rounded-card border border-blue-200/70 space-y-3">
                    <label
                      htmlFor="resolution-value"
                      className="block text-xs font-bold text-content-primary uppercase tracking-wide"
                    >
                      Confirmed Value for {detail.field_key.replace(/_/g, ' ')}
                    </label>
                    <input
                      id="resolution-value"
                      type="text"
                      value={resolutionValue}
                      onChange={(e) => setResolutionValue(e.target.value)}
                      data-testid="resolution-value-input"
                      className="w-full rounded-button bg-white border border-surface-border px-3.5 py-2.5 text-sm font-semibold focus:ring-2 focus:ring-paytm-blue/20 focus:border-paytm-blue transition-all"
                      placeholder="e.g. 50000"
                    />
                    <p className="text-[11px] text-content-secondary">
                      This verified value will be written to the journey snapshot and evaluated deterministically.
                    </p>
                  </div>
                )}

                {/* Sub-Form: REQUEST_ADDITIONAL_INFORMATION */}
                {resolutionType === 'REQUEST_ADDITIONAL_INFORMATION' && (
                  <div className="bg-amber-50/40 p-4 rounded-card border border-amber-200/70 space-y-4">
                    {/* Quick doc chips */}
                    <div className="space-y-1.5">
                      <span className="text-[11px] font-bold text-content-secondary uppercase tracking-wider">
                        Quick Add Document Requirement:
                      </span>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {QUICK_DOC_TAGS.map((tag) => (
                          <button
                            key={tag}
                            type="button"
                            onClick={() => addDocTag(tag)}
                            className="text-[11px] font-semibold bg-white border border-amber-300 hover:border-amber-500 hover:bg-amber-50 text-amber-900 px-2.5 py-1 rounded-full transition-all"
                          >
                            + {tag}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div>
                      <label
                        htmlFor="requested-docs"
                        className="block text-xs font-bold text-content-primary mb-1 uppercase tracking-wide"
                      >
                        Requested Documents (Comma-separated)
                      </label>
                      <input
                        id="requested-docs"
                        type="text"
                        value={requestedDocsInput}
                        onChange={(e) => setRequestedDocsInput(e.target.value)}
                        data-testid="requested-docs-input"
                        className="w-full rounded-button bg-white border border-surface-border px-3.5 py-2 text-sm focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 transition-all"
                        placeholder="e.g. Latest 3-Month Salary Slip, Bank Statement"
                      />
                    </div>

                    <div>
                      <label
                        htmlFor="customer-message"
                        className="block text-xs font-bold text-content-primary mb-1 uppercase tracking-wide"
                      >
                        Message to Customer (Customer Experience Phrasing)
                      </label>
                      <textarea
                        id="customer-message"
                        value={customerMessage}
                        onChange={(e) => setCustomerMessage(e.target.value)}
                        data-testid="customer-message-input"
                        className="w-full rounded-button bg-white border border-surface-border px-3.5 py-2 text-sm focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 transition-all"
                        rows={3}
                        placeholder="Please provide a recent salary slip or bank statement reflecting the declared income so we can proceed with your application."
                      />
                    </div>

                    {/* Real-time Customer Experience Preview */}
                    <div className="bg-white p-3 rounded-button border border-amber-200/80 space-y-1.5 shadow-2xs">
                      <div className="flex items-center gap-1.5 text-[11px] font-bold text-amber-900 uppercase tracking-wider">
                        <HelpCircle className="w-3.5 h-3.5 text-amber-700" />
                        <span>Live Customer Experience Preview</span>
                      </div>
                      <div className="p-2.5 bg-amber-50/50 rounded-sm border border-amber-100 text-xs space-y-1">
                        <p className="font-bold text-content-primary">
                          Action Required: Additional Verification
                        </p>
                        <p className="text-content-secondary">
                          We need: <strong>{requestedDocsInput || 'Specific documents'}</strong>
                        </p>
                        {customerMessage && (
                          <p className="text-content-tertiary italic">
                            &ldquo;{customerMessage}&rdquo;
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* Sub-Form: ESCALATE_FOR_SPECIALIST_REVIEW */}
                {resolutionType === 'ESCALATE_FOR_SPECIALIST_REVIEW' && (
                  <div className="bg-red-50/30 p-4 rounded-card border border-red-200 space-y-3">
                    <Select
                      label="Escalation Category"
                      value={escalationCategory}
                      onChange={(e) => setEscalationCategory(e.target.value)}
                      options={ESCALATION_CATEGORIES}
                    />

                    <div>
                      <label
                        htmlFor="resolution-reason"
                        className="block text-xs font-bold text-content-primary mb-1 uppercase tracking-wide"
                      >
                        Escalation Rationale for Specialist
                      </label>
                      <textarea
                        id="resolution-reason"
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        data-testid="resolution-reason-input"
                        className="w-full rounded-button bg-white border border-surface-border px-3.5 py-2 text-sm focus:ring-2 focus:ring-red-500/20 focus:border-red-500 transition-all"
                        rows={2}
                        placeholder="Explain why standard verification could not proceed..."
                        required
                      />
                    </div>
                  </div>
                )}

                {/* Common Reason Input for other types */}
                {resolutionType !== 'REQUEST_ADDITIONAL_INFORMATION' &&
                  resolutionType !== 'ESCALATE_FOR_SPECIALIST_REVIEW' && (
                    <div className="space-y-3">
                      <div>
                        <label
                          htmlFor="resolution-reason"
                          className="block text-xs font-bold text-content-primary mb-1 uppercase tracking-wide"
                        >
                          Resolution Rationale
                        </label>
                        <textarea
                          id="resolution-reason"
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          data-testid="resolution-reason-input"
                          className="w-full rounded-button bg-white border border-surface-border px-3.5 py-2 text-sm focus:ring-2 focus:ring-paytm-blue/20 focus:border-paytm-blue transition-all"
                          rows={2}
                          placeholder="State why this exception is resolved..."
                          required
                        />
                      </div>

                      <div>
                        <label
                          htmlFor="resolution-notes"
                          className="block text-xs font-bold text-content-primary mb-1 uppercase tracking-wide"
                        >
                          Internal Reviewer Notes (Optional)
                        </label>
                        <textarea
                          id="resolution-notes"
                          value={notes}
                          onChange={(e) => setNotes(e.target.value)}
                          data-testid="resolution-notes-input"
                          className="w-full rounded-button bg-white border border-surface-border px-3.5 py-2 text-sm focus:ring-2 focus:ring-paytm-blue/20 focus:border-paytm-blue transition-all"
                          rows={2}
                          placeholder="Audit documentation or internal observations..."
                        />
                      </div>
                    </div>
                  )}

                {/* Error Banner */}
                {(formError || mutationError) && (
                  <div
                    className="p-3.5 bg-red-50 text-paytm-red text-xs font-semibold rounded-button border border-red-200 flex items-center gap-2"
                    data-testid="resolution-form-error"
                  >
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span>{formError || mapErrorToUxAction(mutationError!).message}</span>
                  </div>
                )}

                {/* Action CTA Button */}
                <div className="pt-2">
                  <Button
                    variant="primary"
                    size="lg"
                    className="w-full sm:w-auto"
                    onClick={handlePreSubmit}
                    data-testid="submit-resolution-btn"
                  >
                    Preview Resolution &amp; Impact
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </div>

        {/* Right Column (1 Col): Journey Context & Lifecycle Audit */}
        <div className="space-y-6">
          <JourneyContextWorkspace detail={detail} />
          <AuditTimelineWorkspace entries={audit?.entries ?? []} />
        </div>
      </div>

      {/* Confirmation Modal (Section 15) */}
      <ReviewActionModal
        isOpen={showConfirm}
        onClose={() => setShowConfirm(false)}
        onConfirm={executeResolution}
        isSubmitting={isSubmitting}
        caseNumber={detail.case_number}
        fieldKey={detail.field_key}
        resolutionType={resolutionType}
        resolutionValue={resolutionValue}
        reason={reason}
        requestedDocs={docsArray}
        customerMessage={customerMessage}
        escalationCategory={escalationCategory}
      />
    </div>
  );
};

export default ReviewCaseDetail;
