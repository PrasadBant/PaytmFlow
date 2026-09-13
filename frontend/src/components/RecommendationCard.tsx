import type { ReactElement } from 'react';
import { Sparkles, ArrowRight, CheckCircle2, LockOpen } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { Badge } from '@/components/primitives/Badge';
import { cn } from '@/lib/utils';
import type { components } from '@/api/types.gen';

export type ActionOption = components['schemas']['ActionOption'];

export interface RecommendationCardProps {
  action: ActionOption;
  onSelect: (action: ActionOption) => void;
  source?: 'AI_RANKED' | 'PLANNER_FALLBACK';
  className?: string;
}

export function RecommendationCard({
  action,
  onSelect,
  source,
  className,
}: RecommendationCardProps): ReactElement {
  const isDevBadges = import.meta.env.VITE_SHOW_DEV_BADGES === 'true';

  return (
    <Card
      data-testid="recommendation-card"
      className={cn(
        'p-6 md:p-8 bg-gradient-to-br from-paytm-blue-50/70 to-surface border-2 border-paytm-blue/30 shadow-card hover:border-paytm-blue/60 transition-all duration-150 relative overflow-hidden',
        className
      )}
    >
      {/* Top badges */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <Badge variant="flagship" icon={<Sparkles className="w-3.5 h-3.5 text-paytm-cyan" />}>
            Recommended Next Action
          </Badge>
          <Badge variant="neutral">
            {action.kind === 'EVIDENCE' ? 'Document Upload' : action.kind === 'FORM' ? 'Details Form' : 'Clarification'}
          </Badge>
        </div>

        {isDevBadges && source && (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface-muted text-content-tertiary border border-surface-border select-none">
            source: {source}
          </span>
        )}
      </div>

      {/* Action Title & Why */}
      <div className="space-y-2 mb-6">
        <h3 className="text-xl md:text-2xl font-bold text-content-primary tracking-tight">
          {action.title}
        </h3>
        {action.why && (
          <p className="text-sm text-content-secondary leading-relaxed">
            {action.why}
          </p>
        )}
      </div>

      {/* Unlocks / Impact Pills */}
      {action.unlocks && action.unlocks.length > 0 && (
        <div className="mb-6 space-y-2">
          <p className="text-xs font-semibold text-content-tertiary uppercase tracking-wider flex items-center gap-1.5">
            <LockOpen className="w-3.5 h-3.5 text-paytm-blue" />
            <span>Unlocks Following Steps</span>
          </p>
          <div className="flex flex-wrap gap-2">
            {action.unlocks.map((unlockKey) => (
              <span
                key={unlockKey}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-badge bg-surface border border-surface-border text-xs font-medium text-content-primary shadow-xs"
              >
                <CheckCircle2 className="w-3 h-3 text-paytm-green" />
                <span>{unlockKey.replace(/_/g, ' ')}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Action CTA */}
      <div className="pt-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-t border-surface-border/60">
        <div className="text-xs text-content-tertiary">
          {action.kind === 'EVIDENCE'
            ? 'PDF, JPEG, or PNG supported (max 10MB)'
            : action.kind === 'FORM'
              ? 'Fill in requested form parameters'
              : 'Answer a quick clarifying question'}
        </div>

        <Button
          variant="primary"
          size="md"
          onClick={() => onSelect(action)}
          className="w-full sm:w-auto px-6 font-bold inline-flex items-center gap-2"
          aria-label={`Take action: ${action.title}`}
        >
          <span>{action.kind === 'CLARIFICATION' ? 'Review' : 'Take Action'}</span>
          <ArrowRight className="w-4 h-4" />
        </Button>
      </div>
    </Card>
  );
}

export default RecommendationCard;
