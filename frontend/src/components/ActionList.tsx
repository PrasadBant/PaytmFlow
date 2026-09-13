import { ChevronRight, FileText, Sliders, UserCheck, ShieldCheck } from 'lucide-react';
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
      return <FileText className="w-5 h-5" />;
    }
    if (id.includes('tenure') || id.includes('amount')) {
      return <Sliders className="w-5 h-5" />;
    }
    if (id.includes('kyc') || id.includes('verify')) {
      return <ShieldCheck className="w-5 h-5" />;
    }
    return <UserCheck className="w-5 h-5" />;
  };

  return (
    <div data-testid="action-list" className={cn('space-y-3.5', className)}>
      <div>
        <h2 className="text-base font-bold text-content-primary tracking-tight">
          Other valid actions
          <span className="sr-only">Alternative Options ({alternatives.length})</span>
        </h2>
      </div>

      <div className="space-y-2.5">
        {alternatives.map((action) => (
          <Card
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
            className="p-4 bg-white border border-surface-border hover:border-paytm-blue-action hover:shadow-card transition-all duration-150 flex items-center justify-between gap-4 cursor-pointer group rounded-card"
          >
            <div className="flex items-center gap-3.5 min-w-0">
              <div className="w-10 h-10 rounded-full bg-blue-50 text-paytm-blue flex items-center justify-center shrink-0 group-hover:bg-paytm-blue-action group-hover:text-white transition-colors">
                {getActionIcon(action)}
              </div>

              <div className="min-w-0 space-y-0.5">
                <h3 className="text-sm font-bold text-content-primary group-hover:text-paytm-blue-action transition-colors truncate">
                  {action.title}
                </h3>
                {action.why && (
                  <p className="text-xs text-content-secondary line-clamp-1">
                    {action.why}
                  </p>
                )}
              </div>
            </div>

            <div className="shrink-0 text-slate-400 group-hover:text-paytm-blue-action transition-colors pr-1">
              <ChevronRight className="w-5 h-5" />
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default ActionList;
