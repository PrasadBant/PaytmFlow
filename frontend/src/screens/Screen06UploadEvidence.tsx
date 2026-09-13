import { useEffect, useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { ArrowLeft, UploadCloud, FileEdit, HelpCircle, ShieldCheck, CheckCircle2, AlertCircle } from 'lucide-react';
import { useJourney } from '@/api/hooks/useJourney';
import { useRecommendation } from '@/api/hooks/useRecommendation';
import { useUploadEvidence } from '@/api/hooks/useUploadEvidence';
import { useApplyAction } from '@/api/hooks/useApplyAction';
import { EvidenceDropzone } from '@/components/EvidenceDropzone';
import { SchemaForm } from '@/components/SchemaForm/SchemaForm';
import { Tabs, type TabItem } from '@/components/primitives/Tabs';
import { Button } from '@/components/primitives/Button';
import { Card } from '@/components/primitives/Card';
import { Spinner } from '@/components/primitives/Spinner';
import { mapErrorToUxAction } from '@/api/errors';
import type { components } from '@/api/types.gen';

type GoalFieldSpec = components['schemas']['GoalFieldSpec'];
type ActionOption = components['schemas']['ActionOption'];

interface LocationState {
  action?: ActionOption;
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

const DEFAULT_MANUAL_SCHEMA: GoalFieldSpec[] = [
  {
    key: 'monthly_income',
    type: 'money',
    label: 'Net Monthly Income',
    required: true,
    placeholder: 'e.g. 85000',
    help_text: 'Enter your monthly in-hand salary or regular business income',
  },
  {
    key: 'employer_name',
    type: 'text',
    label: 'Employer or Organization Name',
    required: true,
    placeholder: 'e.g. Acme Corp',
    help_text: 'Current registered employer or enterprise name',
  },
];

export const Screen06UploadEvidence: React.FC = () => {
  const { id: journeyId, actionId } = useParams<{ id: string; actionId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = (location.state as LocationState) || {};

  const [activeTab, setActiveTab] = useState<'upload' | 'manual' | 'help'>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

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
  const docType = action?.accepts?.[0] || (actionId ? actionId.replace(/^UPLOAD_/, '') : 'DOCUMENT');

  // This route serves every resolve_action_id on Screen 4/5, for every action kind,
  // across all six packs - not just LENDING's income-proof upload. The screen must
  // present differently for a document upload (EVIDENCE) vs. a plain field submission
  // (FORM); there is nothing to "upload" for e.g. ACCEPT_LOAN_TERMS or
  // SUBMIT_EMPLOYMENT_INFO, so that tab (and its evidence-specific copy) is only
  // offered for EVIDENCE-kind actions.
  const isFormAction = action?.kind === 'FORM';
  const screenTitle = action?.title || (isFormAction ? 'Complete This Step' : 'Upload Evidence');

  const tabs: TabItem[] = isFormAction
    ? [
        {
          id: 'manual',
          label: 'Enter Details',
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
    if (!selectedFile || !journeyId || !currentSnapshotId) return;
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
    : DEFAULT_MANUAL_SCHEMA;

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
            <EvidenceDropzone
              onFileSelect={(file) => {
                setSelectedFile(file);
                setSubmitError(null);
              }}
              selectedFile={selectedFile}
              isUploading={uploadEvidence.isPending}
            />

            {/* Why we need this checklist */}
            <div className="p-4 rounded-card bg-surface-subtle border border-surface-border space-y-3">
              <h3 className="text-sm font-bold text-content-primary">
                Why we need this?
              </h3>
              <div className="space-y-2">
                <div className="flex items-center gap-2.5 text-xs sm:text-sm text-content-secondary">
                  <CheckCircle2 className="w-4 h-4 text-paytm-green shrink-0" />
                  <span>Verify your repayment capacity</span>
                </div>
                <div className="flex items-center gap-2.5 text-xs sm:text-sm text-content-secondary">
                  <CheckCircle2 className="w-4 h-4 text-paytm-green shrink-0" />
                  <span>Satisfy required financial criteria</span>
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
                disabled={!selectedFile || uploadEvidence.isPending}
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

            <SchemaForm
              schema={manualSchema}
              submitLabel={
                uploadEvidence.isPending || applyAction.isPending ? 'Submitting...' : 'Submit Details →'
              }
              onSubmit={handleManualSubmit}
              isSubmitting={uploadEvidence.isPending || applyAction.isPending}
            />
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
