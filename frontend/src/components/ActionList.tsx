import { ChevronRight, Briefcase, SlidersHorizontal, UserCheck, ShieldCheck } from 'lucide-react';
import type { ReactElement } from 'react';
import { Card } from '@/components/primitives/Card';
import { cn } from '@/lib/utils';
import type { components } from '@/api/types.gen';

export type ActionOption = components['schemas']['ActionOption'];

export interface ActionListProps {
  alternatives: ActionOption[];
  onSelect: (action: ActionOption) => void;
  className?: string;
}

export function ActionList({
  alternatives,
  onSelect,
  className,
}: ActionListProps): ReactElement | null {
  if (!alternatives || alternatives.length === 0) {
    return null;
  }

  const getActionIcon = (action: ActionOption): ReactElement => {
    const id = action.action_id.toLowerCase();
    if (id.includes('employ') || id.includes('income')) {
      return <Briefcase className="w-4 h-4" />;
    }
    if (id.includes('tenure') || id.includes('amount')) {
      return <SlidersHorizontal className="w-4 h-4" />;
    }
    if (id.includes('kyc') || id.includes('verify')) {
      return <ShieldCheck className="w-4 h-4" />;
    }
    return <UserCheck className="w-4 h-4" />;
  };

  return (
    <div data-testid="action-list" className={cn('space-y-3', className)}>
      <div>
        <h2 className="text-base font-bold text-content-primary tracking-tight">
          Other valid actions
          <span className="sr-only">Alternative Options ({alternatives.length})</span>
        </h2>
      </div>

      {/* Single bordered container with divided rows, matching the reference
          (previously three separate cards). */}
      <Card className="p-0 divide-y divide-surface-border overflow-hidden bg-white border border-surface-border shadow-xs">
        {alternatives.map((action) => (
          <div
            key={action.action_id}
            role="button"
            tabIndex={0}
            aria-label={`Select alternative action: ${action.title}`}
            data-testid={`action-option-${action.action_id}`}
            onClick={() => onSelect(action)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelect(action);
              }
            }}
            className="p-4 flex items-center justify-between gap-4 cursor-pointer group hover:bg-surface-hover transition-colors duration-150"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="text-content-secondary group-hover:text-paytm-blue-action transition-colors shrink-0">
                {getActionIcon(action)}
              </span>
              <span className="text-sm font-semibold text-content-primary group-hover:text-paytm-blue-action transition-colors truncate">
                {action.title}
              </span>
            </div>

            <ChevronRight className="w-4 h-4 text-content-tertiary group-hover:text-paytm-blue-action transition-colors shrink-0" />
          </div>
        ))}
      </Card>
    </div>
  );
}

export default ActionList;
