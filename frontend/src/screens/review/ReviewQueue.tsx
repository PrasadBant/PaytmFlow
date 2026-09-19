import type React from 'react';
import { useState, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  FolderOpen,
  Search,
  Clock,
  ArrowRight,
  User,
  ShieldAlert,
  X,
  SlidersHorizontal,
} from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { Spinner } from '@/components/primitives/Spinner';
import { Select } from '@/components/primitives/Select';
import { StatusBadge } from '@/components/StatusBadge';
import { formatRelativeTime } from '@/lib/utils';
import { mapErrorToUxAction } from '@/api/errors';
import { useReviewQueue, type ReviewQueueFilters, type ReviewCase } from '@/api/hooks/useReview';

const TABS: { id: string; label: string; filters: ReviewQueueFilters }[] = [
  { id: 'ALL', label: 'All Cases', filters: {} },
  { id: 'PENDING', label: 'Needs Attention', filters: { status: 'REVIEW_REQUIRED' } },
  { id: 'MINE', label: 'My Cases', filters: { mine: true } },
  { id: 'WAITING', label: 'Waiting Customer', filters: { status: 'ADDITIONAL_INFO_REQUIRED' } },
  { id: 'ESCALATED', label: 'Escalated', filters: { status: 'ESCALATED' } },
  { id: 'RESOLVED', label: 'Resolved', filters: { status: 'RESOLVED' } },
];

const PRIORITY_WEIGHT: Record<string, number> = {
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1,
};

type SortOption = 'newest' | 'oldest' | 'priority';

function getNextActionHint(c: ReviewCase): { label: string; tone: string } {
  switch (c.status) {
    case 'REVIEW_REQUIRED':
      return { label: 'Review Evidence', tone: 'bg-blue-50 text-paytm-blue-action border-blue-200/60' };
    case 'UNDER_REVIEW':
      return c.assigned_reviewer
        ? { label: 'Continue Review', tone: 'bg-indigo-50 text-indigo-700 border-indigo-200/60' }
        : { label: 'Claim & Review', tone: 'bg-blue-50 text-paytm-blue-action border-blue-200/60' };
    case 'ADDITIONAL_INFO_REQUIRED':
      return { label: 'Waiting on Customer', tone: 'bg-amber-50 text-amber-800 border-amber-200/60' };
    case 'ESCALATED':
      return { label: 'Specialist Triage', tone: 'bg-red-50 text-red-700 border-red-200/60' };
    case 'RESOLVED':
      return { label: 'View Resolution', tone: 'bg-emerald-50 text-emerald-700 border-emerald-200/60' };
    default:
      return { label: 'Open Case', tone: 'bg-slate-50 text-slate-700 border-slate-200/60' };
  }
}

export const ReviewQueue: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const activeTab = searchParams.get('tab') || 'ALL';
  const tab = TABS.find((t) => t.id === activeTab) ?? TABS[0];

  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortOption>('newest');

  const { data, isLoading, error, refetch } = useReviewQueue(tab.filters);

  const filteredAndSortedCases = useMemo(() => {
    let result = data?.cases ? [...data.cases] : [];

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (c) =>
          c.case_number.toLowerCase().includes(q) ||
          c.journey_display_name.toLowerCase().includes(q) ||
          c.reason_title.toLowerCase().includes(q) ||
          c.reason_code.toLowerCase().includes(q) ||
          (c.assigned_reviewer && c.assigned_reviewer.toLowerCase().includes(q))
      );
    }

    result.sort((a, b) => {
      if (sortBy === 'priority') {
        const weightA = PRIORITY_WEIGHT[a.priority] ?? 0;
        const weightB = PRIORITY_WEIGHT[b.priority] ?? 0;
        if (weightA !== weightB) return weightB - weightA;
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }

      const timeA = new Date(a.created_at).getTime();
      const timeB = new Date(b.created_at).getTime();
      return sortBy === 'newest' ? timeB - timeA : timeA - timeB;
    });

    return result;
  }, [data?.cases, searchQuery, sortBy]);

  return (
    <div data-testid="review-queue" className="max-w-7xl mx-auto px-4 py-8 md:py-10 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-surface-border pb-5">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-content-primary tracking-tight">
            Review Queue
          </h1>
          <p className="text-sm text-content-secondary mt-1">
            Prioritize, investigate, and resolve journey exceptions and document ambiguities.
          </p>
          <span data-testid="active-tab" className="sr-only">
            {activeTab}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/review')}
            className="text-xs"
          >
            Dashboard Overview
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 select-none hide-scrollbar" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={activeTab === t.id}
            onClick={() => {
              setSearchParams(t.id === 'ALL' ? {} : { tab: t.id });
              setSearchQuery('');
            }}
            className={`px-4 py-2 rounded-full text-xs font-bold transition-all shrink-0 whitespace-nowrap ${
              activeTab === t.id
                ? 'bg-paytm-blue-action text-white shadow-xs'
                : 'bg-white border border-surface-border text-content-secondary hover:bg-slate-50 hover:text-content-primary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Search & Filter Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between bg-white p-3 rounded-card border border-surface-border shadow-xs">
        <div className="relative flex-1">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-4 w-4 text-content-tertiary" />
          </div>
          <input
            type="text"
            className="w-full rounded-button bg-surface-subtle/50 border border-surface-border pl-9 pr-8 py-2 text-sm focus:outline-hidden focus:ring-2 focus:ring-paytm-blue/20 focus:border-paytm-blue transition-all"
            placeholder="Search by case #, journey, issue, or reviewer..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute inset-y-0 right-0 pr-3 flex items-center text-content-tertiary hover:text-content-primary"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <div className="flex items-center gap-1.5 text-xs text-content-tertiary font-semibold">
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>Sort:</span>
          </div>
          <div className="w-44">
            <Select
              label=""
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              options={[
                { value: 'newest', label: 'Newest First' },
                { value: 'oldest', label: 'Oldest First' },
                { value: 'priority', label: 'Highest Priority' },
              ]}
              className="text-xs"
            />
          </div>
        </div>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div
          data-testid="review-queue-loading"
          className="min-h-[240px] flex items-center justify-center bg-white rounded-card border border-surface-border"
        >
          <Spinner size="lg" className="text-paytm-blue" />
        </div>
      )}

      {/* Error State */}
      {error && (
        <div
          data-testid="review-queue-error"
          className="p-8 rounded-card bg-paytm-red-light border border-red-200 text-center space-y-4 max-w-lg mx-auto"
        >
          <AlertCircle className="w-10 h-10 text-paytm-red mx-auto" />
          <p className="text-sm text-content-secondary">{mapErrorToUxAction(error).message}</p>
          <Button variant="primary" onClick={() => refetch()}>
            Try Again
          </Button>
        </div>
      )}

      {/* Cases List */}
      {!isLoading && !error && filteredAndSortedCases.length > 0 && (
        <div className="space-y-3" data-testid="review-case-list">
          {filteredAndSortedCases.map((c) => {
            const nextAction = getNextActionHint(c);
            const isHighPriority = c.priority === 'HIGH';

            return (
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
                className={`p-4 sm:p-5 bg-white border transition-all rounded-card cursor-pointer group shadow-xs hover:shadow-card hover:border-slate-300 relative ${
                  isHighPriority ? 'border-l-4 border-l-red-500 border-surface-border' : 'border-surface-border'
                }`}
              >
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                  {/* Left info column */}
                  <div className="min-w-0 flex-1 space-y-2">
                    {/* Top pill row */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full ${
                          c.priority === 'HIGH'
                            ? 'bg-red-50 text-red-700 border border-red-200/60'
                            : c.priority === 'MEDIUM'
                            ? 'bg-amber-50 text-amber-800 border border-amber-200/60'
                            : 'bg-slate-100 text-slate-700'
                        }`}
                      >
                        {c.priority} Priority
                      </span>

                      <span className="text-xs font-mono font-bold text-content-primary bg-slate-100 px-2 py-0.5 rounded-sm">
                        {c.case_number}
                      </span>

                      <span className="text-xs font-semibold text-content-secondary">
                        {c.journey_display_name} Journey
                      </span>

                      <span className="text-xs text-content-tertiary">&middot;</span>

                      <span className="text-xs text-content-tertiary font-mono">
                        {c.field_key}
                      </span>
                    </div>

                    {/* Problem title */}
                    <h2 className="text-sm sm:text-base font-extrabold text-content-primary truncate group-hover:text-paytm-blue transition-colors">
                      {c.reason_title}
                    </h2>

                    {/* Problem description */}
                    <p className="text-xs text-content-secondary line-clamp-1">
                      {c.reason_description}
                    </p>

                    {/* Metadata & Assignment footer */}
                    <div className="flex items-center gap-4 text-[11px] font-medium text-content-tertiary flex-wrap pt-0.5">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5" /> Waiting {formatRelativeTime(c.created_at)}
                      </span>

                      {c.assigned_reviewer ? (
                        <span className="inline-flex items-center gap-1 text-indigo-700 font-semibold bg-indigo-50 px-2 py-0.5 rounded-md border border-indigo-200/60">
                          <User className="w-3 h-3" /> Claimed by {c.assigned_reviewer}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-amber-800 font-semibold bg-amber-50 px-2 py-0.5 rounded-md border border-amber-200/60">
                          <ShieldAlert className="w-3 h-3" /> Unassigned
                        </span>
                      )}

                      <span className="hidden sm:inline-block">
                        Updated {formatRelativeTime(c.updated_at)}
                      </span>
                    </div>
                  </div>

                  {/* Right Action & Status column */}
                  <div className="flex flex-row lg:flex-col items-center lg:items-end justify-between lg:justify-center gap-3 shrink-0 pt-2 lg:pt-0 border-t lg:border-t-0 border-surface-border">
                    <StatusBadge status={c.status} size="sm" />

                    {/* Next Action Box */}
                    <div className="flex items-center gap-2">
                      <span className={`text-[11px] font-bold px-2.5 py-1 rounded-full border ${nextAction.tone}`}>
                        {nextAction.label}
                      </span>
                      <ArrowRight className="w-4 h-4 text-content-tertiary group-hover:text-paytm-blue-action group-hover:translate-x-0.5 transition-all" />
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && filteredAndSortedCases.length === 0 && (
        <Card
          data-testid="review-queue-empty"
          className="p-10 text-center space-y-4 border border-surface-border bg-surface-subtle max-w-xl mx-auto rounded-card"
        >
          <div className="w-14 h-14 rounded-full bg-white border border-surface-border shadow-xs text-content-tertiary flex items-center justify-center mx-auto">
            {searchQuery ? <Search className="w-6 h-6 text-content-tertiary" /> : <FolderOpen className="w-6 h-6 text-content-tertiary" />}
          </div>
          <div>
            <h2 className="text-base font-bold text-content-primary">
              {searchQuery ? 'No matching cases' : 'No cases found in this queue'}
            </h2>
            <p className="text-sm text-content-secondary max-w-sm mx-auto mt-1">
              {searchQuery
                ? `No exceptions matched "${searchQuery}". Try searching for another case number, journey, or keyword.`
                : 'No cases currently match the selected filter. Check back when exceptions are flagged by the journey engine.'}
            </p>
          </div>
          {searchQuery ? (
            <Button variant="outline" size="sm" onClick={() => setSearchQuery('')}>
              Clear Search Query
            </Button>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setSearchParams({})}>
              View All Cases
            </Button>
          )}
        </Card>
      )}
    </div>
  );
};

export default ReviewQueue;
