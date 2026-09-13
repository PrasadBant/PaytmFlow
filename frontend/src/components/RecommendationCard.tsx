import type { ReactElement } from 'react';
import { Sparkle, ArrowRight } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
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
      className={cn('p-6 md:p-8 bg-white border border-surface-border shadow-xs', className)}
    >
      {isDevBadges && source && (
        <div className="flex justify-end mb-2">
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface-muted text-content-tertiary border border-surface-border select-none">
            source: {source}
          </span>
        </div>
      )}

      {/* Icon + Title + Why - matches the reference's simple, badge-free layout */}
      <div className="flex items-start gap-3 mb-6">
        <Sparkle className="w-6 h-6 text-paytm-blue-action shrink-0 mt-0.5 fill-paytm-blue-action" aria-hidden="true" />
        <div className="space-y-1.5">
          <h3 className="text-xl md:text-2xl font-bold text-content-primary tracking-tight">
            {action.title}
          </h3>
          {action.why && (
            <p className="text-sm text-content-secondary leading-relaxed">
              {action.why}
            </p>
          )}
          <span className="sr-only">
            {action.kind === 'EVIDENCE' ? 'Document Upload' : action.kind === 'FORM' ? 'Details Form' : 'Clarification'}
          </span>
        </div>
      </div>

      {/* Action CTA - centered, full-width on mobile, matching the reference */}
      <Button
        variant="primary"
        size="lg"
        onClick={() => onSelect(action)}
        className="w-full font-bold inline-flex items-center justify-center gap-2"
        aria-label={`Take action: ${action.title}`}
      >
        <span>{action.kind === 'CLARIFICATION' ? 'Review' : 'Take Action'}</span>
        <ArrowRight className="w-4 h-4" />
      </Button>
    </Card>
  );
}

export default RecommendationCard;
