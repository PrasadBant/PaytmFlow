import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  CheckCircle2,
  AlertCircle,
  Building,
  FileCheck,
  ArrowLeft,
} from 'lucide-react';
import { useJourney } from '@/api/hooks/useJourney';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { Modal } from '@/components/primitives/Modal';
import { Spinner } from '@/components/primitives/Spinner';
import { mapErrorToUxAction } from '@/api/errors';

export const Screen09CompleteJourney: React.FC = () => {
  const { id: journeyId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [isHandoffModalOpen, setIsHandoffModalOpen] = useState(false);

  const {
    data: journey,
    isLoading,
    error,
    refetch,
  } = useJourney(journeyId);

  if (isLoading) {
    return (
      <div
        data-testid="screen-09-loading"
        className="min-h-[400px] flex flex-col items-center justify-center p-8 space-y-4"
      >
        <Spinner size="lg" className="text-paytm-blue" />
        <p className="text-sm font-medium text-content-secondary">
          Loading completion status...
        </p>
      </div>
    );
  }

  if (error || !journey) {
    return (
      <div
        data-testid="screen-09-error"
        className="max-w-page mx-auto p-6 flex flex-col items-center justify-center min-h-[400px] text-center space-y-4"
      >
        <div className="w-12 h-12 rounded-full bg-paytm-red-light text-paytm-red flex items-center justify-center">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-xl font-bold text-content-primary">Unable to load journey</h2>
        <p className="text-sm text-content-secondary max-w-md">
          {error ? mapErrorToUxAction(error).message : 'The requested journey could not be found.'}
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

  // Guard: If journey is NOT READY, show guard banner and redirect option
  if (journey.readiness !== 'READY') {
    return (
      <div data-testid="screen-09-complete-journey" className="max-w-3xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate(`/j/${journey.journey_id}`)}
          className="text-content-secondary hover:text-content-primary -ml-2 mb-2 inline-flex items-center gap-1.5"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Return to Journey Status</span>
        </Button>

        <Card data-testid="not-ready-guard-banner" className="p-8 text-center space-y-4 border border-surface-border">
          <div className="w-12 h-12 rounded-full bg-amber-50 text-amber-600 flex items-center justify-center mx-auto">
            <AlertCircle className="w-6 h-6" />
          </div>
          <h2 className="text-xl font-bold text-content-primary">Journey Not Ready for Completion</h2>
          <p className="text-sm text-content-secondary max-w-md mx-auto">
            This journey still has outstanding verification steps or blockers. Please resolve all items before proceeding to handoff.
          </p>
          <div className="pt-2 flex justify-center gap-3">
            <Button variant="primary" onClick={() => navigate(`/j/${journey.journey_id}`)}>
              View Current Status
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const heading = 'Application Ready!';
  const subtext =
    'All required information is complete. Your application package is ready for handoff.';
  const journeyTitle = journey.display?.title || journey.journey_type.replace(/_/g, ' ');

  return (
    <div
      data-testid="screen-09-complete-journey"
      className="max-w-xl mx-auto px-4 py-10 md:py-14 text-center space-y-8"
    >
      {/* Title & Subtitle with Complete Header */}
      <div data-testid="complete-header" className="space-y-2">
        <div className="flex items-center justify-center gap-2 text-xs font-semibold text-content-secondary mb-1">
          <span className="px-2.5 py-0.5 rounded-full bg-[#e6f9f1] text-[#00b972] font-bold">
            Verification Complete
          </span>
          <span>Snapshot v{journey.version_number}</span>
          <span className="sr-only">{journeyTitle}</span>
        </div>

        <h1
          data-testid="completion-title"
          className="text-3xl sm:text-4xl font-extrabold tracking-tight text-content-primary"
        >
          {heading}
        </h1>
        <p className="text-sm text-content-secondary max-w-md mx-auto leading-relaxed">
          {subtext}
        </p>
      </div>

      {/* Large Green Circular Checkmark with Celebratory Confetti Dots */}
      <div className="relative flex items-center justify-center py-4 select-none">
        <div className="relative w-32 h-32 flex items-center justify-center">
          {/* Confetti / celebratory dots */}
          <div className="absolute top-2 left-6 w-2.5 h-2.5 rounded-full bg-[#00baf2] animate-bounce-subtle" />
          <div className="absolute top-4 right-6 w-3 h-1.5 rounded-sm bg-[#00b972] rotate-45 animate-bounce-subtle" style={{ animationDelay: '0.2s' }} />
          <div className="absolute bottom-6 left-4 w-2 h-2 rounded-full bg-[#ff9900] animate-bounce-subtle" style={{ animationDelay: '0.4s' }} />
          <div className="absolute bottom-4 right-8 w-2.5 h-2.5 rounded-full bg-[#005bf5] animate-bounce-subtle" style={{ animationDelay: '0.15s' }} />
          <div className="absolute top-1 left-16 w-2 h-2 rounded-full bg-[#e53935] animate-bounce-subtle" style={{ animationDelay: '0.35s' }} />
          <div className="absolute top-8 right-2 w-2 h-3 rounded-sm bg-[#00baf2] -rotate-12 animate-bounce-subtle" style={{ animationDelay: '0.25s' }} />

          {/* Central Green Checkmark */}
          <div className="w-20 h-20 rounded-full bg-[#00b972] text-white flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <CheckCircle2 className="w-11 h-11 text-white" />
          </div>
        </div>
      </div>

      {/* Verification Checklist Card - matches the reference's generic 4-line
          checklist. These four statements are generic corollaries of
          `readiness === 'READY'` (guaranteed true by the guard above for every
          pack: no mandatory field can be unsatisfied, no blocker can remain),
          not fabricated per-pack business data, so one fixed list safely
          covers all six packs without any journey-specific branching. */}
      <Card
        data-testid="verification-checklist-section"
        className="p-6 bg-white border border-surface-border shadow-xs rounded-2xl text-left space-y-3.5 max-w-md mx-auto"
      >
        {[
          'All mandatory fields completed',
          'No blockers remaining',
          'Documents verified',
          'Ready for provider handoff',
        ].map((line) => (
          <div key={line} className="flex items-center gap-3 text-sm text-content-primary">
            <div className="w-5 h-5 rounded-full bg-[#00b972] text-white flex items-center justify-center shrink-0">
              <CheckCircle2 className="w-3.5 h-3.5 text-white" />
            </div>
            <span className="font-semibold">{line}</span>
          </div>
        ))}
      </Card>

      {/* Action Buttons */}
      <div className="space-y-3 max-w-md mx-auto pt-2">
        <Button
          variant="primary"
          size="lg"
          className="w-full py-3 text-base font-semibold shadow-xs"
          onClick={() => setIsHandoffModalOpen(true)}
          data-testid="proceed-handoff-btn"
        >
          Proceed to Handoff
        </Button>

        <Button
          variant="secondary"
          size="lg"
          className="w-full py-3 text-base font-semibold"
          onClick={() => navigate(`/j/${journey.journey_id}`)}
          data-testid="review-app-btn"
        >
          Review Application
        </Button>
      </div>

      {/* Handoff Explanation Modal */}
      <Modal
        isOpen={isHandoffModalOpen}
        onClose={() => setIsHandoffModalOpen(false)}
        title="Application Package Ready for Handoff"
        description="Next steps for external partner handoff."
        footer={
          <div className="flex items-center justify-end gap-3 w-full">
            <Button variant="secondary" onClick={() => setIsHandoffModalOpen(false)}>
              Close
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                setIsHandoffModalOpen(false);
                navigate('/my-journeys');
              }}
              data-testid="handoff-done-btn"
            >
              Go to My Journeys
            </Button>
          </div>
        }
      >
        <div data-testid="handoff-modal-content" className="space-y-4 text-sm text-content-secondary">
          <div className="p-4 rounded-card bg-paytm-blue-50 border border-paytm-blue/20 flex items-start gap-3 text-content-primary">
            <Building className="w-5 h-5 text-paytm-blue shrink-0 mt-0.5" />
            <div className="text-xs leading-relaxed space-y-1">
              <p className="font-bold text-paytm-blue">Pre-Application Preparation Notice</p>
              <p>
                PaytmFlow is a readiness preparation and deterministic verification workspace. No actual financial or credit submission takes place inside this application.
              </p>
            </div>
          </div>

          <p>
            Your application package for <strong className="text-content-primary">{journeyTitle}</strong> has met all required verification criteria.
          </p>

          <div className="space-y-2 pt-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-content-primary">
              <FileCheck className="w-4 h-4 text-paytm-green-dark" />
              <span>Verified Package Summary:</span>
            </div>
            <ul className="text-xs list-disc list-inside space-y-1 pl-1">
              <li>All required verification documents and parameters confirmed</li>
              <li>Pre-handoff integrity checks passed (Snapshot v{journey.version_number})</li>
              <li>Ready for handoff to designated financial service partners</li>
            </ul>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default Screen09CompleteJourney;
