import { useEffect, useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { ArrowLeft, UploadCloud, FileEdit, HelpCircle, ShieldCheck, CheckCircle2, AlertCircle, FileWarning } from 'lucide-react';
import { useJourney } from '@/api/hooks/useJourney';
import { useRecommendation } from '@/api/hooks/useRecommendation';
import { useUploadEvidence } from '@/api/hooks/useUploadEvidence';
import { useApplyAction } from '@/api/hooks/useApplyAction';
import { EvidenceDropzone } from '@/components/EvidenceDropzone';
import { SchemaForm } from '@/components/SchemaForm/SchemaForm';
import { SchedulingPicker } from '@/components/interactions/SchedulingPicker';
import { ConsentPanel } from '@/components/interactions/ConsentPanel';
import { VideoVerificationFlow } from '@/components/interactions/VideoVerificationFlow';
import { classifyInteraction } from '@/lib/actionInteraction';
import { Tabs, type TabItem } from '@/components/primitives/Tabs';
import { Button } from '@/components/primitives/Button';
import { Card } from '@/components/primitives/Card';
import { Spinner } from '@/components/primitives/Spinner';
import { Select } from '@/components/primitives/Select';
import { mapErrorToUxAction } from '@/api/errors';
import type { components } from '@/api/types.gen';

type ActionOption = components['schemas']['ActionOption'];

interface LocationState {
  action?: ActionOption;
  snapshotId?: string;
}

function humanizeDocType(docType: string): string {
  return docType
    .toLowerCase()
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
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

// There is deliberately no fallback field list here. EVIDENCE-kind actions
// never carry an input_schema at all (per contract - manual entry for a
// document has no fixed shape the API can define), and a FORM-kind action
// with a missing/empty input_schema is a genuine contract violation. Either
// way, inventing fields to show anyway - the previous "Net Monthly Income" /
// "Employer or Organization Name" fallback - meant every journey's manual-
// entry path could show Lending-specific fields with no relationship to
// what was actually being asked for. When there is no real schema, the
// manual-entry panel must say so and offer a way back, never fabricate one.

export const Screen06UploadEvidence: React.FC = () => {
  const { id: journeyId, actionId } = useParams<{ id: string; actionId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = (location.state as LocationState) || {};

  const [activeTab, setActiveTab] = useState<'upload' | 'manual' | 'help'>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Real-user QA finding (§14.5 / Item 1 closure): when an EVIDENCE action accepts
  // more than one document type (e.g. Lending's UPLOAD_INCOME_PROOF: SALARY_SLIP or
  // BANK_STATEMENT), the frontend cannot know which type the user is actually
  // uploading just by looking at the file - silently declaring `accepts[0]` regardless
  // of the real file meant a genuine bank-statement upload was always declared to the
  // backend as a salary slip. This was previously masked only because AI_PROVIDER=
  // local_ml's classifier overrides the client-declared type when confident
  // (app/evidence/reconcile.py's `effective_doc_type`) - not guaranteed for MockAI/LLM
  // providers, or for a low-confidence local_ml classification. Fix: when there is
  // exactly one accepted type there is no ambiguity, so it is used directly as before;
  // when there are two or more, the user must explicitly pick which type they are
  // uploading before Upload is enabled, and that explicit choice - not a guess - is
  // what gets sent as `doc_type`. The backend remains the authority on the real type
  // regardless (this is advisory routing metadata, per reconcile.py), but the client
  // must stop lying about it by default.
  const [selectedDocType, setSelectedDocType] = useState<string>('');

  const {
    data: journey,
    isLoading: isJourneyLoading,
    error: journeyError,
    refetch: refetchJourney,
  } = useJourney(journeyId);

  const {
    data: recommendationData,
    isLoading: isRecLoading,
  } = useRecommendation(journeyId);

  const uploadEvidence = useUploadEvidence();
  const applyAction = useApplyAction();

  // Find action from location state or recommendation response
  const action: ActionOption | undefined =
    locationState.action ||
    (recommendationData?.recommendation && recommendationData.recommendation.action_id === actionId
      ? recommendationData.recommendation
      : recommendationData?.alternatives?.find((a) => a.action_id === actionId));

  const currentSnapshotId = locationState.snapshotId || journey?.snapshot_id || '';
  const acceptedDocTypes = action?.accepts || [];
  const requiresDocTypeChoice = acceptedDocTypes.length > 1;
  const fallbackDocType = actionId ? actionId.replace(/^UPLOAD_/, '') : 'DOCUMENT';
  // Single accepted type: no ambiguity, use it directly (matches prior behavior).
  // Multiple accepted types: only use the user's explicit selection - never guess
  // accepts[0] - so the Upload button stays disabled until they choose (see below).
  const docType = requiresDocTypeChoice
    ? selectedDocType
    : acceptedDocTypes[0] || fallbackDocType;
  const docTypeOptions = acceptedDocTypes.map((dt) => ({ value: dt, label: humanizeDocType(dt) }));

  // This route serves every resolve_action_id on Screen 4/5, for every action kind,
  // across all six packs - not just LENDING's income-proof upload. The screen must
  // present differently for a document upload (EVIDENCE) vs. a plain field submission
  // (FORM); there is nothing to "upload" for e.g. ACCEPT_LOAN_TERMS or
  // SUBMIT_EMPLOYMENT_INFO, so that tab (and its evidence-specific copy) is only
  // offered for EVIDENCE-kind actions.
  const isFormAction = action?.kind === 'FORM';
  const screenTitle = action?.title || (isFormAction ? 'Complete This Step' : 'Upload Evidence');

  // A refinement on top of `kind: FORM` - never a new wire-level kind (the
  // contract freezes ActionOption.kind to EVIDENCE/FORM/CLARIFICATION; see
  // actionInteraction.ts). Booking a call, giving mandate/agreement consent,
  // and a liveness/video check are real, distinct interactions - not a
  // blank text field - and this is true for whichever pack's action happens
  // to be one of those, never a specific journey by name.
  const interactionType = classifyInteraction(action);

  // Real-user QA finding (BUG-003): ConsentPanel/SchedulingPicker/
  // VideoVerificationFlow all submit `{ [fieldKey]: <value> }` as the action
  // payload. This used to always be `action.unlocks[0]` - the STATE FIELD
  // the action satisfies (e.g. `loan_offer_accepted`), not the actual
  // payload key the backend's `input_schema` requires (e.g. `accept_terms`
  // for Lending's ACCEPT_LOAN_TERMS). The contract's own words: "FORM ->
  // generic action modal rendered from input_schema" - input_schema is the
  // correct, authoritative source whenever the action declares one; falling
  // back to `unlocks[0]` is only correct for the (currently 10 of 11) real
  // consent/scheduling/video actions across all six packs that declare NO
  // input_schema at all, where it happens to coincide with the field the
  // backend's own fallback matching accepts. Deriving this once, generically,
  // here - not per-journey, per-action-id, or hardcoded - fixes every
  // current and future CONSENT/SCHEDULING/VIDEO_VERIFICATION action that
  // declares a real input_schema, not just Lending's.
  const interactionFieldKey = action?.input_schema?.[0]?.key || action?.unlocks?.[0];
  const tabLabel =
    interactionType === 'SCHEDULING'
      ? 'Schedule'
      : interactionType === 'CONSENT'
        ? 'Confirm & Consent'
        : interactionType === 'VIDEO_VERIFICATION'
          ? 'Verify'
          : 'Enter Details';

  const tabs: TabItem[] = isFormAction
    ? [
        {
          id: 'manual',
          label: tabLabel,
          icon: <FileEdit className="w-4 h-4" aria-hidden="true" />,
        },
      ]
    : [
        {
          id: 'upload',
          label: 'Upload File',
          icon: <UploadCloud className="w-4 h-4" aria-hidden="true" />,
        },
        {
          id: 'manual',
          label: 'Enter Details',
          icon: <FileEdit className="w-4 h-4" aria-hidden="true" />,
        },
        {
          id: 'help',
          label: 'How it helps',
          icon: <HelpCircle className="w-4 h-4" aria-hidden="true" />,
        },
      ];

  // activeTab's own default ('upload') predates knowing the action's kind (it's set
  // before the journey/recommendation queries resolve); clamp it to the one tab a
  // FORM action actually offers so the tab bar and the panel shown never disagree.
  const effectiveTab = isFormAction ? 'manual' : activeTab;

  // Defensive guard: this route has no UI for a CLARIFICATION-kind action (per contract,
  // that kind maps to NeedsReviewCard, not Screen 6's upload/form flow). Screen 5 already
  // routes CLARIFICATION elsewhere, but a stale link, bookmark, or manual URL edit could
  // still land here directly - bounce back to Screen 4, which renders NeedsReviewCard for
  // any AMBIGUOUS field, instead of showing a nonsensical upload/form screen for it.
  useEffect(() => {
    if (journeyId && action?.kind === 'CLARIFICATION') {
      navigate(`/j/${journeyId}`, { replace: true });
    }
  }, [journeyId, action?.kind, navigate]);

  const handleFileUpload = async (): Promise<void> => {
    if (!selectedFile || !journeyId || !currentSnapshotId || !docType) return;
    setSubmitError(null);

    try {
      const response = await uploadEvidence.mutateAsync({
        journeyId,
        file: selectedFile,
        doc_type: docType,
        expected_snapshot_id: currentSnapshotId,
      });

      navigate(`/j/${journeyId}/analysis`, {
        state: {
          evidenceResponse: response,
          journeyId,
          actionId,
          snapshotId: currentSnapshotId,
        },
      });
    } catch (err) {
      setSubmitError(mapErrorToUxAction(err).message);
    }
  };

  const handleManualSubmit = async (values: Record<string, unknown>): Promise<void> => {
    if (!journeyId || !currentSnapshotId) return;
    setSubmitError(null);

    // FORM-kind actions (e.g. "Declare Employment Details", "Accept Loan Agreement
    // Terms") carry no document to interpret - they are a direct state mutation, not
    // evidence. Route them straight to POST /actions with the entered field values so
    // the values the applicant typed are the ones actually applied (per Shared
    // Contract: POST /evidence is preview-only and never mutates; POST /actions is the
    // sole mutation endpoint). EVIDENCE-kind actions keep going through the existing
    // evidence -> AI analysis preview flow below.
    if (action?.kind === 'FORM') {
      try {
        const response = await applyAction.mutateAsync({
          journeyId,
          action_id: actionId || action.action_id,
          expected_snapshot_id: currentSnapshotId,
          idempotency_key: generateIdempotencyKey(),
          input: values,
        });

        navigate(`/j/${journeyId}/updated`, {
          state: {
            actionResponse: response,
            journeyId,
          },
        });
      } catch (err) {
        setSubmitError(mapErrorToUxAction(err).message);
      }
      return;
    }

    if (!docType) {
      setSubmitError('Please select which document type this information is from before submitting.');
      return;
    }

    try {
      const response = await uploadEvidence.mutateAsync({
        journeyId,
        manual_fields: values,
        doc_type: docType,
        expected_snapshot_id: currentSnapshotId,
      });

      navigate(`/j/${journeyId}/analysis`, {
        state: {
          evidenceResponse: response,
          journeyId,
          actionId,
          snapshotId: currentSnapshotId,
        },
      });
    } catch (err) {
      setSubmitError(mapErrorToUxAction(err).message);
    }
  };

  if (isJourneyLoading || isRecLoading) {
    return (
      <div
        data-testid="screen-06-loading"
        className="min-h-[400px] flex flex-col items-center justify-center p-8 space-y-4"
      >
        <Spinner size="lg" className="text-paytm-blue" />
        <p className="text-sm font-medium text-content-secondary">
          Loading evidence requirements...
        </p>
      </div>
    );
  }

  if (journeyError || !journey) {
    return (
      <div
        data-testid="screen-06-error"
        className="max-w-page mx-auto p-6 flex flex-col items-center justify-center min-h-[400px] text-center space-y-4"
      >
        <div className="w-12 h-12 rounded-full bg-paytm-red-light text-paytm-red flex items-center justify-center">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-xl font-bold text-content-primary">Unable to load journey</h2>
        <p className="text-sm text-content-secondary max-w-md">
          {journeyError ? mapErrorToUxAction(journeyError).message : 'Journey information could not be retrieved.'}
        </p>
        <Button variant="secondary" onClick={() => refetchJourney()}>
          Try Again
        </Button>
      </div>
    );
  }

  if (action?.kind === 'CLARIFICATION') {
    // Mid-redirect (see the guard effect above) - render nothing rather than flashing
    // the wrong screen while navigate() takes effect.
    return (
      <div
        data-testid="screen-06-loading"
        className="min-h-[400px] flex flex-col items-center justify-center p-8 space-y-4"
      >
        <Spinner size="lg" className="text-paytm-blue" />
      </div>
    );
  }

  const manualSchema = action?.input_schema && action.input_schema.length > 0
    ? action.input_schema
    : null;

  return (
    <div data-testid="screen-06-upload-evidence" className="max-w-3xl mx-auto px-4 py-8 md:py-10 space-y-6">
      {/* Top Navigation */}
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
          {screenTitle}
        </h1>
      </div>

      {/* Tabs Header - FORM actions get a single "Enter Details" tab (no upload/help
          copy, which is only meaningful for EVIDENCE actions); EVIDENCE actions keep
          all 3 tabs. */}
      <Tabs
        tabs={tabs}
        activeTab={effectiveTab}
        onChange={(tabId) => {
          setActiveTab(tabId as 'upload' | 'manual' | 'help');
          setSubmitError(null);
        }}
        variant="underline"
        className="w-full border-b border-surface-border"
      />

      {/* Global Submit Error Banner */}
      {submitError && (
        <div
          data-testid="evidence-submit-error"
          className="p-4 rounded-card bg-paytm-red-light border border-paytm-red/20 flex items-start gap-3 text-paytm-red"
        >
          <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
          <div className="text-sm font-medium">{submitError}</div>
        </div>
      )}

      {/* Tab Panels */}
      {effectiveTab === 'upload' && (
        <div
          id="tabpanel-upload"
          role="tabpanel"
          aria-labelledby="tab-upload"
          data-testid="tabpanel-upload"
          className="space-y-6"
        >
          <Card className="p-6 md:p-8 space-y-6 bg-white border border-surface-border shadow-xs rounded-card">
            {requiresDocTypeChoice && (
              <Select
                label="Which document are you uploading?"
                required
                helperText="This step accepts more than one document type - tell us which one you have so it's reviewed correctly."
                options={docTypeOptions}
                value={selectedDocType}
                onChange={(e) => setSelectedDocType(e.target.value)}
                data-testid="doc-type-select"
              />
            )}

            <EvidenceDropzone
              onFileSelect={(file) => {
                setSelectedFile(file);
                setSubmitError(null);
              }}
              selectedFile={selectedFile}
              isUploading={uploadEvidence.isPending}
            />

            {/* Why we need this checklist. The specific reason (first line) must come
                from the action's own `why` (the same field the "How it helps" tab
                below already reads) - never a hardcoded loan-specific sentence,
                which previously showed on every journey's every evidence upload
                regardless of what was actually being requested (e.g. "Verify your
                repayment capacity" under a health-insurance medical-records
                upload). Only the two closing lines are journey-agnostic truths
                that hold for any action on any pack. */}
            <div className="p-4 rounded-card bg-surface-subtle border border-surface-border space-y-3">
              <h3 className="text-sm font-bold text-content-primary">
                Why we need this?
              </h3>
              <div className="space-y-2">
                <div className="flex items-center gap-2.5 text-xs sm:text-sm text-content-secondary">
                  <CheckCircle2 className="w-4 h-4 text-paytm-green shrink-0" />
                  <span>{action?.why || 'Required to satisfy this journey’s verification criteria'}</span>
                </div>
                <div className="flex items-center gap-2.5 text-xs sm:text-sm text-content-secondary">
                  <CheckCircle2 className="w-4 h-4 text-paytm-green shrink-0" />
                  <span>Confirms this requirement is satisfied</span>
                </div>
                <div className="flex items-center gap-2.5 text-xs sm:text-sm text-content-secondary">
                  <CheckCircle2 className="w-4 h-4 text-paytm-green shrink-0" />
                  <span>Move to the next step</span>
                </div>
              </div>
            </div>

            {/* Bottom Actions */}
            <div className="flex items-center justify-between gap-4 pt-4 border-t border-surface-border">
              <Button
                type="button"
                variant="secondary"
                onClick={() => navigate(`/j/${journeyId}/next`)}
                disabled={uploadEvidence.isPending}
                className="px-6 py-2.5"
              >
                Cancel
              </Button>

              <Button
                type="button"
                variant="primary"
                onClick={handleFileUpload}
                disabled={!selectedFile || !docType || uploadEvidence.isPending}
                data-testid="upload-submit-btn"
                className="px-8 py-2.5"
              >
                {uploadEvidence.isPending ? (
                  <>
                    <Spinner size="sm" className="mr-2" />
                    <span>Uploading...</span>
                  </>
                ) : (
                  <span>Upload</span>
                )}
              </Button>
            </div>
          </Card>
        </div>
      )}

      {effectiveTab === 'manual' && (
        <div
          id="tabpanel-manual"
          role="tabpanel"
          aria-labelledby="tab-manual"
          data-testid="tabpanel-manual"
          className="space-y-6"
        >
          <Card className="p-6 space-y-6">
            {interactionType === 'SCHEDULING' ? (
              <SchedulingPicker
                actionTitle={screenTitle}
                why={action?.why}
                fieldKey={interactionFieldKey}
                submitLabel={applyAction.isPending ? 'Submitting...' : 'Confirm Slot →'}
                isSubmitting={applyAction.isPending}
                onSubmit={handleManualSubmit}
              />
            ) : interactionType === 'CONSENT' ? (
              <ConsentPanel
                actionTitle={screenTitle}
                why={action?.why}
                fieldKey={interactionFieldKey}
                submitLabel={applyAction.isPending ? 'Submitting...' : 'Confirm →'}
                isSubmitting={applyAction.isPending}
                onSubmit={handleManualSubmit}
              />
            ) : interactionType === 'VIDEO_VERIFICATION' ? (
              <VideoVerificationFlow
                actionTitle={screenTitle}
                why={action?.why}
                fieldKey={interactionFieldKey}
                submitLabel={applyAction.isPending ? 'Submitting...' : 'Continue →'}
                isSubmitting={applyAction.isPending}
                onSubmit={handleManualSubmit}
              />
            ) : manualSchema ? (
              <>
                <div className="space-y-1">
                  <h2 className="text-base font-semibold text-content-primary">
                    {isFormAction ? 'Enter Details' : 'Enter Details Manually'}
                  </h2>
                  <p className="text-xs text-content-secondary">
                    {isFormAction
                      ? 'Fill in the information below to complete this step.'
                      : 'Do not have the document handy? You can enter the required information directly below.'}
                  </p>
                </div>

                {!isFormAction && requiresDocTypeChoice && (
                  <Select
                    label="Which document is this information from?"
                    required
                    helperText="This step accepts more than one document type - tell us which one you're entering details for."
                    options={docTypeOptions}
                    value={selectedDocType}
                    onChange={(e) => setSelectedDocType(e.target.value)}
                    data-testid="doc-type-select-manual"
                  />
                )}

                <SchemaForm
                  schema={manualSchema}
                  submitLabel={
                    uploadEvidence.isPending || applyAction.isPending ? 'Submitting...' : 'Submit Details →'
                  }
                  onSubmit={handleManualSubmit}
                  isSubmitting={uploadEvidence.isPending || applyAction.isPending}
                />
              </>
            ) : (
              <div data-testid="manual-entry-unavailable" className="flex flex-col items-center text-center gap-4 py-6">
                <div className="w-12 h-12 rounded-full bg-surface-subtle text-content-tertiary flex items-center justify-center">
                  <FileWarning className="w-6 h-6" />
                </div>
                <div className="space-y-1 max-w-sm">
                  <h2 className="text-base font-semibold text-content-primary">
                    Details entry isn&apos;t available for this {isFormAction ? 'step' : 'document'} yet.
                  </h2>
                  <p className="text-xs text-content-secondary">
                    {isFormAction
                      ? 'This step has no configured form yet. Please go back and try again later.'
                      : 'Manual entry isn’t set up for this document type. Please upload the file instead, or come back to it later.'}
                  </p>
                </div>
                <div className="flex items-center gap-3 pt-2">
                  {!isFormAction && (
                    <Button
                      type="button"
                      variant="primary"
                      onClick={() => {
                        setActiveTab('upload');
                        setSubmitError(null);
                      }}
                      data-testid="manual-unavailable-back-to-upload-btn"
                    >
                      Back to Upload
                    </Button>
                  )}
                  <Button
                    type="button"
                    variant={isFormAction ? 'primary' : 'secondary'}
                    onClick={() => navigate(`/j/${journeyId}`)}
                    data-testid="manual-unavailable-return-btn"
                  >
                    Return to Journey Status
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => navigate(`/j/${journeyId}/next`)}
                    data-testid="manual-unavailable-cancel-btn"
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </div>
      )}

      {effectiveTab === 'help' && (
        <div
          id="tabpanel-help"
          role="tabpanel"
          aria-labelledby="tab-help"
          data-testid="tabpanel-help"
          className="space-y-4"
        >
          <Card className="p-6 space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-paytm-blue-50 text-paytm-blue flex items-center justify-center shrink-0">
                <CheckCircle2 className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <h3 className="text-base font-semibold text-content-primary">
                  Why is this evidence requested?
                </h3>
                <p className="text-sm text-content-secondary leading-relaxed">
                  {action?.why ||
                    'Verifying this document satisfies required criteria on your journey and allows unlocking subsequent steps.'}
                </p>
              </div>
            </div>

            <div className="pt-4 border-t border-surface-border space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-content-tertiary">
                What we verify
              </h4>
              <ul className="space-y-2 text-sm text-content-secondary">
                <li className="flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-paytm-blue mt-2 shrink-0" />
                  <span>Document authenticity and matching name/identity information.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-paytm-blue mt-2 shrink-0" />
                  <span>Required numerical values such as income or financial statements.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-paytm-blue mt-2 shrink-0" />
                  <span>Date validity and period relevance.</span>
                </li>
              </ul>
            </div>

            <div className="pt-4 border-t border-surface-border flex items-start gap-3 bg-surface-subtle p-3.5 rounded-card">
              <ShieldCheck className="w-5 h-5 text-paytm-green shrink-0 mt-0.5" />
              <div className="text-xs text-content-secondary leading-relaxed">
                <strong className="text-content-primary block font-medium">Safe & Deterministic Processing</strong>
                Your data is parsed deterministically to verify field requirements without any black-box scoring or hidden calculations.
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};

export default Screen06UploadEvidence;
