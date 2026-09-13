import type { ReactElement, ReactNode, ComponentType } from 'react';
import { FolderOpen } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { cn } from '@/lib/utils';

export interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: ComponentType<{ className?: string }>;
  action?: {
    label: string;
    onClick: () => void;
    variant?: 'primary' | 'secondary' | 'ghost';
    icon?: ComponentType<{ className?: string }>;
  };
  children?: ReactNode;
  className?: string;
}

export function EmptyState({
  title = 'No Records Found',
  description = 'There are no items to display at this time.',
  icon: Icon = FolderOpen,
  action,
  children,
  className,
}: EmptyStateProps): ReactElement {
  const ActionIcon = action?.icon;

  return (
    <div
      data-testid="empty-state"
      className={cn('max-w-xl mx-auto p-4 md:p-6 text-center', className)}
    >
      <Card className="p-8 md:p-10 text-center bg-surface border-surface-border shadow-card space-y-5">
        <div className="w-12 h-12 mx-auto rounded-full bg-surface-subtle text-content-secondary flex items-center justify-center shrink-0">
          <Icon className="w-6 h-6" aria-hidden="true" />
        </div>

        <div className="space-y-1.5">
          <h2 className="text-lg md:text-xl font-bold text-content-primary tracking-tight">
            {title}
          </h2>
          <p className="text-sm text-content-secondary leading-relaxed max-w-md mx-auto">
            {description}
          </p>
        </div>

        {children && <div className="text-left pt-2">{children}</div>}

        {action && (
          <div className="pt-3 flex justify-center">
            <Button
              variant={action.variant || 'primary'}
              onClick={action.onClick}
              data-testid="empty-state-action-btn"
            >
              {ActionIcon && <ActionIcon className="w-4 h-4 mr-1.5" />}
              <span>{action.label}</span>
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}

export default EmptyState;
