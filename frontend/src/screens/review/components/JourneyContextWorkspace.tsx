import type React from 'react';
import { Compass, AlertTriangle, ArrowRight, CheckCircle2, Circle, AlertCircle } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { StatusBadge } from '@/components/StatusBadge';
import { JourneyDiff } from '@/components/JourneyDiff';
import type { ReviewCaseDetail } from '@/api/hooks/useReview';

interface JourneyContextWorkspaceProps {
  detail: ReviewCaseDetail;
}

export const JourneyContextWorkspace: React.FC<JourneyContextWorkspaceProps> = ({ detail }) => {
  const fields = detail.journey_context?.fields ?? [];
  const currentBlockerField = fields.find((f) => f.key === detail.field_key);

  return (
    <div className="space-y-6" data-testid="journey-context-workspace">
      {/* Current Blocker Hero Card */}
      <Card padding="md" className="bg-red-50/40 border border-red-200/80 shadow-xs space-y-2">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-red-800">
          <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
          <span>Current Active Blocker</span>
        </div>
        <p className="text-sm font-extrabold text-content-primary">
          {currentBlockerField?.label || detail.field_key} ({detail.reason_title})
        </p>
        <p className="text-xs text-content-secondary leading-relaxed">
          The customer journey cannot proceed past this stage until this exception is resolved, additional documents are provided, or the case is formally escalated.
        </p>
      </Card>

      {/* Complete Journey Steps Checklist */}
      <Card padding="md" className="bg-white border border-surface-border shadow-xs space-y-4">
        <div className="flex items-center justify-between border-b border-surface-border pb-3">
          <div className="flex items-center gap-2">
            <Compass className="w-4 h-4 text-paytm-blue-action" />
            <h3 className="text-sm font-bold text-content-primary">Journey Structure</h3>
          </div>
          <span className="text-[10px] uppercase font-bold text-content-tertiary tracking-wider bg-slate-100 px-2 py-0.5 rounded-sm">
            Live State
          </span>
        </div>

        <div className="space-y-2">
          {fields.map((f) => {
            const isBlocker = f.key === detail.field_key;

            return (
              <div
                key={f.key}
                className={`flex flex-col gap-1 p-2.5 rounded-md transition-colors border ${
                  isBlocker
                    ? 'bg-amber-50/60 border-amber-200'
                    : 'bg-white border-transparent hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    {f.status === 'SATISFIED' ? (
                      <CheckCircle2 className="w-4 h-4 text-paytm-green shrink-0" />
                    ) : isBlocker ? (
                      <AlertCircle className="w-4 h-4 text-paytm-amber shrink-0" />
                    ) : (
                      <Circle className="w-4 h-4 text-content-tertiary shrink-0" />
                    )}
                    <span
                      className={`text-xs font-semibold truncate ${
                        isBlocker ? 'text-amber-950 font-bold' : 'text-content-secondary'
                      }`}
                    >
                      {f.label}
                    </span>
                  </div>
                  <StatusBadge status={f.status} size="sm" />
                </div>

                {f.display_value && (
                  <span className="text-[11px] text-content-tertiary truncate font-mono pl-6">
                    {f.display_value}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {/* Deterministic Impact Preview */}
      <Card padding="md" className="bg-white border border-surface-border shadow-xs space-y-3">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-paytm-blue-action border-b border-surface-border pb-2.5">
          <ArrowRight className="w-4 h-4" />
          <span>Anticipated Journey Impact</span>
        </div>

        {detail.impact_preview ? (
          <div className="space-y-2">
            <p className="text-xs text-content-secondary">
              Deterministic dry-run preview if resolved with evidence value:
            </p>
            <div className="rounded-button border border-surface-border overflow-hidden bg-slate-50/50 p-2">
              <JourneyDiff diff={detail.impact_preview} variant="preview" />
            </div>
          </div>
        ) : (
          <div className="space-y-2.5 text-xs text-content-secondary">
            <div className="flex items-center justify-between p-2 rounded-sm bg-slate-50 border border-surface-border">
              <span className="text-content-tertiary">Current State:</span>
              <span className="font-bold text-amber-800 bg-amber-50 px-2 py-0.5 rounded-sm">
                EXCEPTION BLOCKED
              </span>
            </div>
            <div className="flex items-center justify-between p-2 rounded-sm bg-slate-50 border border-surface-border">
              <span className="text-content-tertiary">After Resolution:</span>
              <span className="font-bold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded-sm">
                EXCEPTION SATISFIED
              </span>
            </div>
            <div className="flex items-center justify-between p-2 rounded-sm bg-slate-50 border border-surface-border">
              <span className="text-content-tertiary">Next Evaluation:</span>
              <span className="font-bold text-paytm-blue">Deterministic Rule Engine</span>
            </div>
            <p className="text-[11px] text-content-tertiary italic pt-1 leading-relaxed">
              * Resolving unblocks the field. The journey engine then deterministically evaluates readiness. Reviewers do not manually approve/reject credit decisions.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
};

export default JourneyContextWorkspace;
