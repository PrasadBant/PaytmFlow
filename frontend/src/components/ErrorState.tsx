import type { ReactElement, ReactNode } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { cn } from '@/lib/utils';

export interface ErrorStateProps {
  title?: string;
  message?: string;
  errorCode?: string;
  onRetry?: () => void;
  isRetrying?: boolean;
  retryLabel?: string;
  action?: {
    label: string;
    onClick: () => void;
    variant?: 'primary' | 'secondary' | 'ghost';
  };
  children?: ReactNode;
  className?: string;
}

export function ErrorState({
  title = 'Unable to Load Data',
  message = 'An unexpected error occurred while processing your request.',
  errorCode,
  onRetry,
  isRetrying = false,
  retryLabel = 'Try Again',
  action,
  children,
  className,
}: ErrorStateProps): ReactElement {
  return (
    <div
      data-testid="error-state"
      role="alert"
      className={cn('max-w-xl mx-auto p-4 md:p-6', className)}
    >
      <Card className="p-6 md:p-8 text-center bg-surface border-paytm-red/30 shadow-card space-y-5">
        <div className="w-12 h-12 mx-auto rounded-full bg-paytm-red-light text-paytm-red flex items-center justify-center shrink-0">
          <AlertCircle className="w-6 h-6" aria-hidden="true" />
        </div>

        <div className="space-y-1.5">
          <h2 className="text-lg md:text-xl font-bold text-content-primary tracking-tight">
            {title}
          </h2>
          <p className="text-sm text-content-secondary leading-relaxed max-w-md mx-auto">
            {message}
          </p>
          {errorCode && (
            <p className="text-xs font-mono text-paytm-red bg-paytm-red-light/60 px-2.5 py-1 rounded inline-block mt-2">
              Code: {errorCode}
            </p>
          )}
        </div>

        {children && <div className="text-left">{children}</div>}

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
          {onRetry && (
            <Button
              variant="primary"
              onClick={onRetry}
              disabled={isRetrying}
              data-testid="error-retry-btn"
              className="w-full sm:w-auto"
            >
              <RefreshCw className={cn('w-4 h-4 mr-1.5', isRetrying && 'animate-spin')} />
              <span>{isRetrying ? 'Retrying...' : retryLabel}</span>
            </Button>
          )}

          {action && (
            <Button
              variant={action.variant || 'secondary'}
              onClick={action.onClick}
              data-testid="error-action-btn"
              className="w-full sm:w-auto"
            >
              {action.label}
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}

export default ErrorState;
