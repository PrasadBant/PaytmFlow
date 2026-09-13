import type { ReactElement } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/primitives/Button';
import { cn } from '@/lib/utils';

export interface StaleBannerProps {
  message?: string;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  className?: string;
}

export function StaleBanner({
  message = 'This journey has moved on — refreshing with latest state.',
  onRefresh,
  isRefreshing = false,
  className,
}: StaleBannerProps): ReactElement {
  return (
    <div
      data-testid="stale-banner"
      role="alert"
      className={cn(
        'p-4 rounded-card bg-paytm-amber-light border border-amber-300 text-amber-900 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3',
        className
      )}
    >
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-amber-200/80 text-amber-900 flex items-center justify-center shrink-0">
          <AlertTriangle className="w-4 h-4" />
        </div>
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-amber-800">
            Outdated Snapshot Detected
          </p>
          <p className="text-sm font-medium text-amber-950 mt-0.5">{message}</p>
        </div>
      </div>

      {onRefresh && (
        <Button
          variant="secondary"
          size="sm"
          onClick={onRefresh}
          disabled={isRefreshing}
          data-testid="stale-refresh-btn"
          className="self-end sm:self-center shrink-0 border-amber-300 bg-white text-amber-900 hover:bg-amber-50"
        >
          <RefreshCw className={cn('w-3.5 h-3.5 mr-1.5', isRefreshing && 'animate-spin')} />
          <span>{isRefreshing ? 'Refreshing...' : 'Refresh Now'}</span>
        </Button>
      )}
    </div>
  );
}

export default StaleBanner;
