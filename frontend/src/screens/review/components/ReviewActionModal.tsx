import type React from 'react';
import { ShieldCheck, AlertTriangle, HelpCircle, ArrowUpCircle } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import type { ReviewResolutionType } from '@/api/hooks/useReview';

interface ReviewActionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  isSubmitting: boolean;
  caseNumber: string;
  fieldKey: string;
  resolutionType: ReviewResolutionType;
  resolutionValue: string;
  reason: string;
  requestedDocs: string[];
  customerMessage: string;
  escalationCategory: string;
}

export const ReviewActionModal: React.FC<ReviewActionModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  isSubmitting,
  caseNumber,
  fieldKey,
  resolutionType,
  resolutionValue,
  reason,
  requestedDocs,
  customerMessage,
  escalationCategory,
}) => {
  if (!isOpen) return null;

  const isResolveSufficient = resolutionType === 'EVIDENCE_SUFFICIENT';
  const isRequestInfo = resolutionType === 'REQUEST_ADDITIONAL_INFORMATION';
  const isEscalate = resolutionType === 'ESCALATE_FOR_SPECIALIST_REVIEW';
  const isCorrection = resolutionType === 'CUSTOMER_INFO_NEEDS_CORRECTION';
  const isCannotVerify = resolutionType === 'EVIDENCE_CANNOT_BE_VERIFIED';

  const getActionTitle = () => {
    if (isResolveSufficient) return 'Resolve Evidence as Sufficient';
    if (isRequestInfo) return 'Request Additional Information from Customer';
    if (isEscalate) return 'Escalate Case to Underwriting Specialist';
    if (isCorrection) return 'Mark Customer Information as Needing Correction';
    if (isCannotVerify) return 'Mark Evidence as Unverifiable';
    return 'Confirm Exception Action';
  };

  const getCustomerImpact = () => {
    if (isResolveSufficient) {
      return `Customer's ${fieldKey.replace(/_/g, ' ')} will be updated to ₹${resolutionValue}, unblocking the journey.`;
    }
    if (isRequestInfo) {
      return `Customer will receive an immediate action request to upload: ${requestedDocs.join(', ')}. Journey remains blocked until submitted.`;
    }
    if (isEscalate) {
      return 'Customer remains in a pending review state while a specialist investigates policy exceptions.';
    }
    if (isCorrection) {
      return 'Customer will be asked to correct their input declaration.';
    }
    return 'Customer will be notified that the evidence could not be verified.';
  };

  const getJourneyImpact = () => {
    if (isResolveSufficient) {
      return 'Deterministic journey engine will re-evaluate readiness. Downstream stages unlock automatically if all rules pass.';
    }
    if (isRequestInfo) {
      return 'Case moves to ADDITIONAL_INFO_REQUIRED. Handoff loop pauses awaiting customer response.';
    }
    if (isEscalate) {
      return 'Case moves to ESCALATED status in the specialist queue. No credit approval or rejection occurs.';
    }
    return 'Case is closed. Journey status is recalculated.';
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/45 backdrop-blur-xs animate-in fade-in duration-150"
    >
      <Card
        padding="lg"
        className="w-full max-w-lg bg-white shadow-xl space-y-5 rounded-card border border-surface-border"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-surface-border pb-4">
          <div className="flex items-center gap-2.5">
            <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${
              isResolveSufficient
                ? 'bg-emerald-50 text-emerald-700'
                : isRequestInfo
                ? 'bg-amber-50 text-amber-700'
                : isEscalate
                ? 'bg-red-50 text-red-700'
                : 'bg-blue-50 text-paytm-blue-action'
            }`}>
              {isResolveSufficient && <ShieldCheck className="w-5 h-5" />}
              {isRequestInfo && <HelpCircle className="w-5 h-5" />}
              {isEscalate && <ArrowUpCircle className="w-5 h-5" />}
              {!isResolveSufficient && !isRequestInfo && !isEscalate && <AlertTriangle className="w-5 h-5" />}
            </div>
            <div>
              <h2 className="text-lg font-extrabold text-content-primary">
                {getActionTitle()}
              </h2>
              <p className="text-xs text-content-secondary font-mono">
                Case {caseNumber} &middot; {fieldKey}
              </p>
            </div>
          </div>
        </div>

        {/* Structured Impact Summary */}
        <div className="bg-surface-subtle/50 p-4 rounded-button border border-surface-border space-y-3.5 text-xs">
          {/* Action Row */}
          <div className="grid grid-cols-[110px_1fr] gap-2 items-baseline">
            <span className="font-bold text-content-tertiary uppercase tracking-wider text-[10px]">Action</span>
            <span className="font-bold text-content-primary text-xs">
              {resolutionType.replace(/_/g, ' ')}
            </span>
          </div>

          {/* Specific Parameters */}
          {isResolveSufficient && (
            <div className="grid grid-cols-[110px_1fr] gap-2 items-baseline">
              <span className="font-bold text-content-tertiary uppercase tracking-wider text-[10px]">Confirmed Value</span>
              <span className="font-mono font-extrabold text-content-primary text-sm text-emerald-700">
                ₹{resolutionValue}
              </span>
            </div>
          )}

          {isRequestInfo && (
            <>
              <div className="grid grid-cols-[110px_1fr] gap-2 items-baseline">
                <span className="font-bold text-content-tertiary uppercase tracking-wider text-[10px]">Requesting</span>
                <span className="font-semibold text-content-primary">
                  {requestedDocs.join(', ')}
                </span>
              </div>
              <div className="grid grid-cols-[110px_1fr] gap-2 items-baseline">
                <span className="font-bold text-content-tertiary uppercase tracking-wider text-[10px]">Customer Notice</span>
                <span className="italic text-content-secondary">
                  &ldquo;{customerMessage}&rdquo;
                </span>
              </div>
            </>
          )}

          {isEscalate && (
            <div className="grid grid-cols-[110px_1fr] gap-2 items-baseline">
              <span className="font-bold text-content-tertiary uppercase tracking-wider text-[10px]">Category</span>
              <span className="font-bold text-red-700">
                {escalationCategory}
              </span>
            </div>
          )}

          {reason && (
            <div className="grid grid-cols-[110px_1fr] gap-2 items-baseline">
              <span className="font-bold text-content-tertiary uppercase tracking-wider text-[10px]">Reviewer Rationale</span>
              <span className="font-medium text-content-primary">
                {reason}
              </span>
            </div>
          )}

          {/* Customer Impact */}
          <div className="grid grid-cols-[110px_1fr] gap-2 items-baseline border-t border-surface-border/70 pt-2.5">
            <span className="font-bold text-paytm-blue uppercase tracking-wider text-[10px]">Customer Impact</span>
            <span className="font-semibold text-content-primary">
              {getCustomerImpact()}
            </span>
          </div>

          {/* Journey Impact */}
          <div className="grid grid-cols-[110px_1fr] gap-2 items-baseline border-t border-surface-border/70 pt-2.5">
            <span className="font-bold text-paytm-blue uppercase tracking-wider text-[10px]">Journey Impact</span>
            <span className="font-semibold text-content-primary">
              {getJourneyImpact()}
            </span>
          </div>
        </div>

        {/* Warning / Disclaimers */}
        <p className="text-[11px] text-content-tertiary text-center leading-relaxed">
          This operational action is audited under your reviewer session. Deterministic engine re-evaluates rules post-resolution.
        </p>

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-3 pt-2 border-t border-surface-border">
          <Button variant="outline" size="sm" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={onConfirm}
            isLoading={isSubmitting}
            data-testid="confirm-resolution-btn"
          >
            Confirm Resolution
          </Button>
        </div>
      </Card>
    </div>
  );
};

export default ReviewActionModal;
