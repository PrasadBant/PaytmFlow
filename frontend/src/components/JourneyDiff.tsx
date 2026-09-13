import type { ReactElement } from 'react';
import { ArrowRight, Plus, Minus, Layers } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Badge } from '@/components/primitives/Badge';
import { StatusBadge } from '@/components/StatusBadge';
import { cn } from '@/lib/utils';
import type { components } from '@/api/types.gen';

type JourneyDiffType = components['schemas']['JourneyDiff'];

export interface JourneyDiffProps {
  diff: JourneyDiffType | null | undefined;
  variant: 'preview' | 'applied';
  className?: string;
}

export function JourneyDiff({
  diff,
  variant,
  className,
}: JourneyDiffProps): ReactElement | null {
  if (!diff) return null;

  const isPreview = variant === 'preview';
  const heading = isPreview ? 'What will change' : 'What changed';
  const subtext = isPreview
    ? 'Predicted state differences before this action is applied.'
    : 'State differences applied and verified in this update.';

  const {
    from_version,
    to_version,
    fields_changed = [],
    actions_unlocked = [],
    actions_removed = [],
    readiness,
    progress,
  } = diff;

  const isEmpty =
    fields_changed.length === 0 &&
    actions_unlocked.length === 0 &&
    actions_removed.length === 0;

  return (
    <Card
      data-testid="journey-diff-card"
      className={cn('p-5 space-y-4 border border-surface-border bg-surface shadow-xs', className)}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-content-primary" data-testid="diff-heading">
              {heading}
            </h3>
            <span
              className={cn(
                'text-xs font-semibold px-2 py-0.5 rounded-full',
                isPreview
                  ? 'bg-paytm-blue-50 text-paytm-blue'
                  : 'bg-paytm-green-light text-paytm-green-dark'
              )}
            >
              {isPreview ? 'Preview' : 'Applied'}
            </span>
          </div>
          <p className="text-xs text-content-secondary">{subtext}</p>
        </div>

        {from_version !== undefined && to_version !== undefined && (
          <div
            data-testid="version-badge"
            className="flex items-center gap-1.5 text-xs font-bold text-content-secondary px-2.5 py-1 rounded-card bg-surface-subtle border border-surface-border shrink-0"
          >
            <span>v{from_version}</span>
            <ArrowRight className="w-3.5 h-3.5 text-content-tertiary" />
            <span className="text-paytm-blue font-extrabold">v{to_version}</span>
          </div>
        )}
      </div>

      {isEmpty ? (
        <div
          data-testid="empty-diff-message"
          className="text-xs text-content-secondary italic py-2 text-center"
        >
          No state differences detected.
        </div>
      ) : (
        <div className="space-y-4 pt-2 border-t border-surface-border">
          {/* 1. Fields Changed List */}
          {fields_changed.length > 0 && (
            <div className="space-y-2" data-testid="fields-changed-section">
              <h4 className="text-xs font-bold uppercase tracking-wider text-content-tertiary">
                Field Status Updates
              </h4>

              <div className="space-y-2">
                {fields_changed.map((field) => (
                  <div
                    key={field.key}
                    data-testid={`diff-field-${field.key}`}
                    className="p-3 rounded-card bg-surface-subtle border border-surface-border/60 flex flex-col sm:flex-row sm:items-center justify-between gap-2"
                  >
                    <div className="space-y-0.5 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-content-primary truncate">
                          {field.label || field.key}
                        </span>
                        {field.cascaded && (
                          <Badge
                            variant="neutral"
                            showDefaultIcon={false}
                            className="text-[10px] py-0 px-1.5 bg-slate-200 text-slate-700 font-medium inline-flex items-center gap-0.5"
                            data-testid={`cascaded-badge-${field.key}`}
                          >
                            <Layers className="w-2.5 h-2.5" />
                            <span>Cascaded</span>
                          </Badge>
                        )}
                      </div>

                      {field.display_value && (
                        <div className="text-xs text-content-secondary font-medium">
                          Value: <span className="text-content-primary">{field.display_value}</span>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <StatusBadge status={field.from_status} size="sm" />
                      <ArrowRight className="w-3.5 h-3.5 text-content-tertiary" />
                      <StatusBadge status={field.to_status} size="sm" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 2. Actions Unlocked */}
          {actions_unlocked.length > 0 && (
            <div className="space-y-1.5" data-testid="actions-unlocked-section">
              <h4 className="text-xs font-bold uppercase tracking-wider text-paytm-green">
                Actions Unlocked
              </h4>
              <div className="flex flex-wrap gap-2">
                {actions_unlocked.map((actionId) => (
                  <span
                    key={actionId}
                    data-testid={`unlocked-action-${actionId}`}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-card bg-paytm-green-light text-paytm-green-dark border border-green-200"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>{actionId}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 3. Actions Removed */}
          {actions_removed.length > 0 && (
            <div className="space-y-1.5" data-testid="actions-removed-section">
              <h4 className="text-xs font-bold uppercase tracking-wider text-content-tertiary">
                Actions Completed / Retired
              </h4>
              <div className="flex flex-wrap gap-2">
                {actions_removed.map((actionId) => (
                  <span
                    key={actionId}
                    data-testid={`removed-action-${actionId}`}
                    className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-card bg-surface-subtle text-content-secondary border border-surface-border line-through"
                  >
                    <Minus className="w-3.5 h-3.5" />
                    <span>{actionId}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 4. Readiness and Progress Transitions */}
          {(readiness?.from !== readiness?.to || (progress?.from && progress?.to)) && (
            <div
              data-testid="diff-transitions"
              className="pt-3 border-t border-surface-border flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
            >
              {readiness?.from && readiness?.to && readiness.from !== readiness.to && (
                <div className="flex items-center gap-2">
                  <span className="text-content-secondary font-medium">Readiness:</span>
                  <StatusBadge status={readiness.from} size="sm" />
                  <ArrowRight className="w-3.5 h-3.5 text-content-tertiary" />
                  <StatusBadge status={readiness.to} size="sm" />
                </div>
              )}

              {progress?.from && progress?.to && (
                <div className="flex items-center gap-1.5 text-content-secondary font-medium sm:ml-auto">
                  <span>Progress:</span>
                  <span className="font-semibold text-content-primary">
                    {progress.from.completed}/{progress.from.total}
                  </span>
                  <ArrowRight className="w-3.5 h-3.5 text-content-tertiary" />
                  <span className="font-semibold text-paytm-blue">
                    {progress.to.completed}/{progress.to.total} Completed
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

export default JourneyDiff;
