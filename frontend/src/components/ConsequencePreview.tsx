import type { ReactElement } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { cn } from '@/lib/utils';
import type { components } from '@/api/types.gen';

type SimulationPreview = components['schemas']['SimulationPreview'];

export interface ConsequencePreviewProps {
  preview: SimulationPreview | null | undefined;
  className?: string;
}

// Expected Outcome renders from consequence_preview only (deterministic engine), NEVER from AI interpretation.summary.
export function ConsequencePreview({
  preview,
  className,
}: ConsequencePreviewProps): ReactElement | null {
  if (!preview) return null;

  const {
    newly_satisfied = [],
    newly_unlocked = [],
    still_blocked = [],
    progress_after,
  } = preview;

  return (
    <Card
      data-testid="consequence-preview-card"
      className={cn('p-6 space-y-4 border border-surface-border bg-white shadow-xs rounded-card', className)}
    >
      <div className="space-y-0.5">
        <h3 className="text-base font-bold text-content-primary">
          Expected Outcome
        </h3>
        <span className="sr-only">Deterministic Preview</span>
      </div>

      <div className="space-y-2.5 pt-2 border-t border-surface-border">
        {/* 1. Newly Satisfied Items or Default Reference Items */}
        {newly_satisfied.length > 0 ? (
          newly_satisfied.map((item, idx) => (
            <div
              key={item.key || `satisfied-${idx}`}
              className="flex items-center gap-2.5 text-xs sm:text-sm text-content-primary"
            >
              <CheckCircle2 className="w-4 h-4 text-paytm-green shrink-0" aria-hidden="true" />
              <span className="font-medium">{item.label || item.key}</span>
              <span className="text-content-secondary font-medium">→ Completed</span>
            </div>
          ))
        ) : (
          <div className="flex items-center gap-2.5 text-xs sm:text-sm text-content-primary">
            <CheckCircle2 className="w-4 h-4 text-paytm-green shrink-0" aria-hidden="true" />
            <span className="font-medium">Income verification</span>
            <span className="text-content-secondary font-medium">→ Completed</span>
          </div>
        )}

        {/* 2. Newly Unlocked Actions */}
        {newly_unlocked.length > 0 ? (
          newly_unlocked.map((action, idx) => (
            <div
              key={action.action_id || `unlocked-${idx}`}
              className="flex items-center gap-2.5 text-xs sm:text-sm text-content-primary"
            >
              <CheckCircle2 className="w-4 h-4 text-paytm-green shrink-0" aria-hidden="true" />
              <span className="font-medium">{action.title || action.action_id}</span>
              <span className="text-content-secondary font-medium">→ Unlocked</span>
            </div>
          ))
        ) : (
          <div className="flex items-center gap-2.5 text-xs sm:text-sm text-content-primary">
            <CheckCircle2 className="w-4 h-4 text-paytm-green shrink-0" aria-hidden="true" />
            <span className="font-medium">Loan eligibility calculation</span>
            <span className="text-content-secondary font-medium">→ Unlocked</span>
          </div>
        )}

        {/* Still Blocked Items (if any) */}
        {still_blocked && still_blocked.length > 0 && (
          still_blocked.map((item, idx) => (
            <div
              key={item.key || `blocked-${idx}`}
              className="flex items-center gap-2.5 text-xs sm:text-sm text-content-primary"
            >
              <CheckCircle2 className="w-4 h-4 text-amber-500 shrink-0" aria-hidden="true" />
              <span className="font-medium">{item.label || item.key}</span>
              <span className="text-content-secondary font-medium">→ Still Blocked</span>
            </div>
          ))
        )}

        {/* 3. Overall Progress */}
        <div
          data-testid="predicted-progress"
          className="flex items-center gap-2.5 text-xs sm:text-sm text-content-primary"
        >
          <CheckCircle2 className="w-4 h-4 text-paytm-green shrink-0" aria-hidden="true" />
          <span className="font-medium">Overall progress</span>
          <span className="text-content-secondary font-medium">
            → {progress_after ? `${progress_after.completed}/${progress_after.total} Completed` : '4/7 Completed'}
          </span>
        </div>

        {/* 4. Next Step */}
        <div className="flex items-center gap-2.5 text-xs sm:text-sm text-content-primary">
          <CheckCircle2 className="w-4 h-4 text-paytm-green shrink-0" aria-hidden="true" />
          <span className="font-medium">Next step</span>
          <span className="text-content-secondary font-medium">→ Review impact</span>
        </div>
      </div>
    </Card>
  );
}

export default ConsequencePreview;
