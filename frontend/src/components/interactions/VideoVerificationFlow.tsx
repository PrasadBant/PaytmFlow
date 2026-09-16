import { useEffect, useState, type ReactElement } from 'react';
import { Video, ShieldCheck, CheckCircle2, Loader2 } from 'lucide-react';
import { Button } from '@/components/primitives/Button';

export interface VideoVerificationFlowProps {
  actionTitle: string;
  why?: string | null;
  /** The payload key the backend actually expects for this action's
   * submitted value - the caller must derive this from the action's own
   * `input_schema[0].key` when declared, falling back to
   * `ActionOption.unlocks[0]` (the state field this action resolves) only
   * when no input_schema exists. Passing `unlocks[0]` unconditionally was
   * a real, user-reported bug (BUG-003) whenever an action declared an
   * input_schema key different from what it satisfies - see
   * Screen06UploadEvidence.tsx's `interactionFieldKey`. */
  fieldKey?: string | null;
  submitLabel: string;
  isSubmitting?: boolean;
  onSubmit: (values: Record<string, unknown>) => void | Promise<void>;
}

type Stage = 'intro' | 'permission' | 'in_progress' | 'complete';

// No real video/biometric verification provider exists in this prototype
// (there is nothing to call - PaytmFlow's own scope explicitly excludes
// live provider integrations). Rather than silently treating a video-KYC
// or liveness-capture action as a plain document upload - which falsely
// implies a photo/video file is all that's being verified - this renders a
// distinct, honestly-labeled simulated flow. It never claims a real
// verification occurred; every stage says "simulated."
export function VideoVerificationFlow({
  actionTitle,
  why,
  fieldKey,
  submitLabel,
  isSubmitting = false,
  onSubmit,
}: VideoVerificationFlowProps): ReactElement {
  const [stage, setStage] = useState<Stage>('intro');

  useEffect(() => {
    if (stage !== 'in_progress') return;
    const timer = setTimeout(() => setStage('complete'), 1800);
    return () => clearTimeout(timer);
  }, [stage]);

  return (
    <div data-testid="video-verification-flow" className="space-y-5">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-full bg-paytm-blue-50 text-paytm-blue flex items-center justify-center shrink-0">
          <Video className="w-5 h-5" />
        </div>
        <div className="space-y-1">
          <h2 className="text-base font-semibold text-content-primary">{actionTitle}</h2>
          <p className="text-xs text-content-secondary leading-relaxed">
            {why || 'A short live verification is required to continue.'}
          </p>
        </div>
      </div>

      <div className="p-3 rounded-card bg-paytm-blue-50 border border-paytm-blue/20 text-xs text-paytm-blue font-medium">
        Video verification is simulated in this prototype - no camera is accessed and no real
        verification provider is contacted.
      </div>

      <div
        className="rounded-card border border-surface-border bg-surface-subtle p-8 flex flex-col items-center justify-center text-center gap-4 min-h-[220px]"
        role="status"
        aria-live="polite"
        data-testid="video-stage-region"
      >
        {stage === 'intro' && (
          <>
            <div className="w-16 h-16 rounded-full bg-white border border-surface-border flex items-center justify-center">
              <Video className="w-7 h-7 text-content-tertiary" />
            </div>
            <div className="space-y-1 max-w-xs">
              <p className="text-sm font-semibold text-content-primary">Ready when you are</p>
              <p className="text-xs text-content-secondary">
                You&apos;ll be asked to allow camera access for a brief liveness check.
              </p>
            </div>
            <Button
              type="button"
              variant="primary"
              onClick={() => setStage('permission')}
              data-testid="video-start-btn"
            >
              Start Verification
            </Button>
          </>
        )}

        {stage === 'permission' && (
          <>
            <div className="w-16 h-16 rounded-full bg-white border border-surface-border flex items-center justify-center">
              <ShieldCheck className="w-7 h-7 text-paytm-blue" />
            </div>
            <div className="space-y-1 max-w-xs">
              <p className="text-sm font-semibold text-content-primary">Camera access (simulated)</p>
              <p className="text-xs text-content-secondary">
                In a real session this would request your camera. Here, continuing simulates
                granting access.
              </p>
            </div>
            <Button
              type="button"
              variant="primary"
              onClick={() => setStage('in_progress')}
              data-testid="video-allow-btn"
            >
              Allow &amp; Continue
            </Button>
          </>
        )}

        {stage === 'in_progress' && (
          <>
            <Loader2 className="w-10 h-10 text-paytm-blue animate-spin" aria-hidden="true" />
            <div className="space-y-1">
              <p className="text-sm font-semibold text-content-primary">Verifying...</p>
              <p className="text-xs text-content-secondary">Simulated liveness check in progress</p>
            </div>
          </>
        )}

        {stage === 'complete' && (
          <>
            <div className="w-16 h-16 rounded-full bg-[#00b972] text-white flex items-center justify-center">
              <CheckCircle2 className="w-8 h-8" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-semibold text-content-primary">Verification complete</p>
              <p className="text-xs text-content-secondary">Simulated result recorded for this journey</p>
            </div>
          </>
        )}
      </div>

      <Button
        type="button"
        variant="primary"
        size="lg"
        className="w-full"
        disabled={stage !== 'complete' || isSubmitting}
        isLoading={isSubmitting}
        onClick={() =>
          void onSubmit({ [fieldKey || 'video_verification_status']: 'completed_simulated' })
        }
        data-testid="video-continue-btn"
      >
        {submitLabel}
      </Button>
    </div>
  );
}

export default VideoVerificationFlow;
