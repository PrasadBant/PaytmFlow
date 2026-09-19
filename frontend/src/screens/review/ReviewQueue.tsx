import type React from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { AlertCircle, FolderOpen } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { Spinner } from '@/components/primitives/Spinner';
import { StatusBadge } from '@/components/StatusBadge';
import { formatRelativeTime } from '@/lib/utils';
import { mapErrorToUxAction } from '@/api/errors';
import { useReviewQueue, type ReviewQueueFilters } from '@/api/hooks/useReview';

const TABS: { id: string; label: string; filters: ReviewQueueFilters }[] = [
  { id: 'ALL', label: 'All', filters: {} },
  { id: 'PENDING', label: 'Pending', filters: { status: 'REVIEW_REQUIRED' } },
  { id: 'MINE', label: 'My Cases', filters: { mine: true } },
  { id: 'WAITING', label: 'Waiting Customer', filters: { status: 'ADDITIONAL_INFO_REQUIRED' } },
  { id: 'ESCALATED', label: 'Escalated', filters: { status: 'ESCALATED' } },
  { id: 'RESOLVED', label: 'Resolved', filters: { status: 'RESOLVED' } },
];

export const ReviewQueue: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const activeTab = searchParams.get('tab') || 'ALL';
  const tab = TABS.find((t) => t.id === activeTab) ?? TABS[0];

  const { data, isLoading, error, refetch } = useReviewQueue(tab.filters);
  const cases = data?.cases ?? [];

  return (
    <div data-testid="review-queue" className="max-w-5xl mx-auto px-4 py-8 md:py-10 space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-content-primary tracking-tight">
          Review Queue
        </h1>
        <span data-testid="active-tab" className="sr-only">
          {activeTab}
        </span>
      </div>

      <div className="flex items-center gap-2 overflow-x-auto pb-2 select-none" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={activeTab === t.id}
            onClick={() => setSearchParams(t.id === 'ALL' ? {} : { tab: t.id })}
            className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all shrink-0 ${
              activeTab === t.id
                ? 'bg-paytm-blue-action text-white shadow-xs'
                : 'bg-white text-content-secondary border border-surface-border hover:bg-slate-50'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isLoading && (
        <div
          data-testid="review-queue-loading"
          className="min-h-[200px] flex items-center justify-center"
        >
          <Spinner size="lg" className="text-paytm-blue" />
        </div>
      )}

      {error && (
        <div
          data-testid="review-queue-error"
          className="p-8 rounded-card bg-paytm-red-light border border-red-200 text-center space-y-4 max-w-lg"
        >
          <AlertCircle className="w-10 h-10 text-paytm-red mx-auto" />
          <p className="text-sm text-content-secondary">{mapErrorToUxAction(error).message}</p>
          <Button variant="primary" onClick={() => refetch()}>
            Try Again
          </Button>
        </div>
      )}

      {!isLoading && !error && cases.length > 0 && (
        <div className="space-y-3" data-testid="review-case-list">
          {cases.map((c) => (
            <Card
              key={c.case_id}
              data-testid={`review-case-row-${c.case_id}`}
              onClick={() => navigate(`/review/case/${c.case_id}`)}
              role="button"
              tabIndex={0}
              aria-label={`Open case ${c.case_number}`}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  navigate(`/review/case/${c.case_id}`);
                }
              }}
              className="p-4 sm:p-5 bg-white border border-surface-border shadow-xs hover:shadow-card hover:border-slate-300 transition-all rounded-card cursor-pointer"
            >
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0 space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-content-tertiary">
                      {c.case_number}
                    </span>
                    <h2 className="text-sm font-bold text-content-primary truncate">
                      {c.reason_title}
                    </h2>
                  </div>
                  <p className="text-xs text-content-secondary truncate">
                    {c.journey_display_name} · {c.field_key}
                  </p>
                  {c.assigned_reviewer && (
                    <p className="text-[11px] text-content-tertiary">
                      Assigned: {c.assigned_reviewer}
                    </p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0 text-right">
                  <StatusBadge status={c.status} size="sm" />
                  <span className="text-[11px] text-content-tertiary">
                    {formatRelativeTime(c.created_at)}
                  </span>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {!isLoading && !error && cases.length === 0 && (
        <Card
          data-testid="review-queue-empty"
          className="p-10 text-center space-y-4 border border-surface-border bg-surface-subtle/50 max-w-lg rounded-card"
        >
          <div className="w-12 h-12 rounded-full bg-surface-subtle border border-surface-border text-content-tertiary flex items-center justify-center mx-auto">
            <FolderOpen className="w-6 h-6" />
          </div>
          <h2 className="text-base font-bold text-content-primary">No cases in this view</h2>
          <p className="text-xs text-content-secondary max-w-sm mx-auto">
            Nothing here right now - check back once a journey needs exception resolution.
          </p>
        </Card>
      )}
    </div>
  );
};

export default ReviewQueue;
