import type React from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock, Eye, Hourglass, ArrowUpCircle, CheckCircle2, AlertCircle } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Spinner } from '@/components/primitives/Spinner';
import { Button } from '@/components/primitives/Button';
import { useReviewDashboard } from '@/api/hooks/useReview';
import { mapErrorToUxAction } from '@/api/errors';

const METRIC_TILES: {
  key: 'pending_review' | 'under_review' | 'waiting_customer' | 'escalated' | 'resolved_today';
  label: string;
  icon: React.FC<{ className?: string }>;
  tone: string;
}[] = [
  { key: 'pending_review', label: 'Pending Review', icon: Clock, tone: 'text-paytm-blue-action' },
  { key: 'under_review', label: 'Under Review', icon: Eye, tone: 'text-paytm-blue' },
  { key: 'waiting_customer', label: 'Waiting Customer', icon: Hourglass, tone: 'text-paytm-amber' },
  { key: 'escalated', label: 'Escalated', icon: ArrowUpCircle, tone: 'text-paytm-red' },
  { key: 'resolved_today', label: 'Resolved Today', icon: CheckCircle2, tone: 'text-paytm-green' },
];

export const ReviewDashboard: React.FC = () => {
  const navigate = useNavigate();
  const { data, isLoading, error, refetch } = useReviewDashboard();

  return (
    <div
      data-testid="review-dashboard"
      className="max-w-5xl mx-auto px-4 py-8 md:py-10 space-y-6"
    >
      <div>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-content-primary tracking-tight">
          PaytmFlow Review Center
        </h1>
        <p className="text-sm text-content-secondary mt-1">
          Resolve exceptional cases and keep financial journeys moving.
        </p>
      </div>

      {isLoading && (
        <div
          data-testid="review-dashboard-loading"
          className="min-h-[200px] flex items-center justify-center"
        >
          <Spinner size="lg" className="text-paytm-blue" />
        </div>
      )}

      {error && (
        <div
          data-testid="review-dashboard-error"
          className="p-8 rounded-card bg-paytm-red-light border border-red-200 text-center space-y-4 max-w-lg"
        >
          <AlertCircle className="w-10 h-10 text-paytm-red mx-auto" />
          <p className="text-sm text-content-secondary">{mapErrorToUxAction(error).message}</p>
          <Button variant="primary" onClick={() => refetch()}>
            Try Again
          </Button>
        </div>
      )}

      {data && (
        <>
          <div
            className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4"
            data-testid="review-metric-grid"
          >
            {METRIC_TILES.map((tile) => (
              <Card
                key={tile.key}
                padding="md"
                data-testid={`metric-${tile.key}`}
                className="bg-white border border-surface-border"
              >
                <tile.icon className={`w-5 h-5 mb-2 ${tile.tone}`} aria-hidden="true" />
                <p className="text-2xl font-extrabold text-content-primary">{data[tile.key]}</p>
                <p className="text-xs text-content-secondary mt-0.5">{tile.label}</p>
              </Card>
            ))}
          </div>

          <div className="flex gap-3">
            <Button variant="primary" onClick={() => navigate('/review/queue')}>
              Open Review Queue
            </Button>
          </div>
        </>
      )}
    </div>
  );
};

export default ReviewDashboard;
