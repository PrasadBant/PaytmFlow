import { useState, type ReactElement } from 'react';
import { FileCheck2 } from 'lucide-react';
import { Button } from '@/components/primitives/Button';

export interface ConsentPanelProps {
  actionTitle: string;
  why?: string | null;
  /** The state field this action resolves (ActionOption.unlocks[0]). */
  fieldKey?: string | null;
  submitLabel: string;
  isSubmitting?: boolean;
  onSubmit: (values: Record<string, unknown>) => void | Promise<void>;
}

// Reusable for any SIGN_*/ACCEPT_*/CONFIRM_*/*MANDATE* FORM action - a
// mandate, an agreement, or a declaration is fundamentally "read this, then
// explicitly agree," not a blank field to type a value into. The action's
// own `why` supplies what's being agreed to; nothing here is journey-specific.
export function ConsentPanel({
  actionTitle,
  why,
  fieldKey,
  submitLabel,
  isSubmitting = false,
  onSubmit,
}: ConsentPanelProps): ReactElement {
  const [agreed, setAgreed] = useState(false);

  return (
    <div data-testid="consent-panel" className="space-y-5">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-full bg-paytm-blue-50 text-paytm-blue flex items-center justify-center shrink-0">
          <FileCheck2 className="w-5 h-5" />
        </div>
        <div className="space-y-1">
          <h2 className="text-base font-semibold text-content-primary">{actionTitle}</h2>
          <p className="text-xs text-content-secondary leading-relaxed">
            {why || 'Review and confirm to proceed.'}
          </p>
        </div>
      </div>

      <label className="flex items-start gap-3 p-4 rounded-card border border-surface-border bg-surface-subtle cursor-pointer">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-0.5 w-4 h-4 accent-paytm-blue shrink-0"
          data-testid="consent-checkbox"
        />
        <span className="text-sm text-content-primary leading-relaxed">
          I have read and agree to the above.
        </span>
      </label>

      <Button
        type="button"
        variant="primary"
        size="lg"
        className="w-full"
        disabled={!agreed || isSubmitting}
        isLoading={isSubmitting}
        onClick={() => void onSubmit({ [fieldKey || 'consent_given']: true })}
        data-testid="consent-confirm-btn"
      >
        {submitLabel}
      </Button>
    </div>
  );
}

export default ConsentPanel;
