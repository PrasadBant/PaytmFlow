import type React from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock, Eye, Hourglass, ArrowUpCircle, CheckCircle2, AlertCircle, ArrowRight, ShieldCheck, UserCheck, Inbox } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Spinner } from '@/components/primitives/Spinner';
import { Button } from '@/components/primitives/Button';
import { useReviewDashboard, useReviewQueue } from '@/api/hooks/useReview';
import { useRoleStore } from '@/state/role';
import { mapErrorToUxAction } from '@/api/errors';
import { StatusBadge } from '@/components/StatusBadge';
import { formatRelativeTime } from '@/lib/utils';

interface MetricTileConfig {
  key: 'pending_review' | 'under_review' | 'waiting_customer' | 'escalated' | 'resolved_today';
  label: string;
  tabTarget: string;
  icon: React.FC<{ className?: string }>;
  tone: string;
  bgTone: string;
  description: string;
}

const METRIC_TILES: MetricTileConfig[] = [
  {
    key: 'pending_review',
    label: 'Needs Attention',
    tabTarget: 'PENDING',
    icon: Clock,
    tone: 'text-paytm-blue-action',
    bgTone: 'bg-blue-50',
    description: 'Awaiting triage or review',
  },
  {
    key: 'under_review',
    label: 'My Active Cases',
    tabTarget: 'MINE',
    icon: Eye,
    tone: 'text-paytm-blue',
    bgTone: 'bg-indigo-50',
    description: 'Claimed and in progress',
  },
  {
    key: 'waiting_customer',
    label: 'Waiting Customer',
    tabTarget: 'WAITING',
    icon: Hourglass,
    tone: 'text-paytm-amber',
    bgTone: 'bg-amber-50',
    description: 'Awaiting requested information',
  },
  {
    key: 'escalated',
    label: 'Escalated',
    tabTarget: 'ESCALATED',
    icon: ArrowUpCircle,
    tone: 'text-paytm-red',
    bgTone: 'bg-red-50',
    description: 'Requires specialist review',
  },
  {
    key: 'resolved_today',
    label: 'Resolved Today',
    tabTarget: 'RESOLVED',
    icon: CheckCircle2,
    tone: 'text-paytm-green',
    bgTone: 'bg-emerald-50',
    description: 'Exceptions closed today',
  },
];

export const ReviewDashboard: React.FC = () => {
  const navigate = useNavigate();
  const currentRole = useRoleStore((s) => s.role);
  const { data, isLoading, error, refetch } = useReviewDashboard();

  // Fetch "Needs Attention" cases (Pending review)
  const { data: pendingQueue, isLoading: pendingLoading } = useReviewQueue({ status: 'REVIEW_REQUIRED' });
  // Fetch "My Cases" (Claimed by current reviewer)
  const { data: myQueue, isLoading: myLoading } = useReviewQueue({ mine: true });

  const urgentCases = pendingQueue?.cases?.slice(0, 5) || [];
  const activeCases = myQueue?.cases?.slice(0, 3) || [];

  return (
    <div
      data-testid="review-dashboard"
      className="max-w-7xl mx-auto px-4 py-8 md:py-10 space-y-8"
    >
      {/* Top Banner / Operational Context */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-surface-border pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-paytm-blue-action bg-blue-50 px-2.5 py-0.5 rounded-full border border-blue-200/60">
              <ShieldCheck className="w-3.5 h-3.5" /> Operations Workspace
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-content-tertiary">
              <UserCheck className="w-3.5 h-3.5 text-emerald-600" />
              Role: {currentRole === 'REVIEW_OFFICER' ? 'Review Officer' : 'Customer View'}
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-content-primary tracking-tight">
            Review Center Dashboard
          </h1>
          <p className="text-sm text-content-secondary mt-1 max-w-2xl">
            Triage exceptions, verify conflicting customer evidence, and unblock journeys via deterministic evaluation.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/review/queue')}
            className="whitespace-nowrap"
          >
            Full Review Queue
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate('/review/queue?tab=PENDING')}
            className="whitespace-nowrap"
          >
            Start Next Case
          </Button>
        </div>
      </div>

      {isLoading && (
        <div
          data-testid="review-dashboard-loading"
          className="min-h-[220px] flex items-center justify-center bg-white rounded-card border border-surface-border"
        >
          <Spinner size="lg" className="text-paytm-blue" />
        </div>
      )}

      {error && (
        <div
          data-testid="review-dashboard-error"
          className="p-8 rounded-card bg-paytm-red-light border border-red-200 text-center space-y-4 max-w-lg mx-auto"
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
          {/* 5-Column Metrics Grid */}
          <div
            className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4"
            data-testid="review-metric-grid"
          >
            {METRIC_TILES.map((tile) => (
              <Card
                key={tile.key}
                padding="md"
                data-testid={`metric-${tile.key}`}
                onClick={() => navigate(`/review/queue?tab=${tile.tabTarget}`)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigate(`/review/queue?tab=${tile.tabTarget}`);
                  }
                }}
                className="bg-white border border-surface-border shadow-xs hover:shadow-card hover:border-slate-300 transition-all cursor-pointer relative overflow-hidden group select-none"
              >
                <div className={`absolute top-0 right-0 w-16 h-16 rounded-bl-full ${tile.bgTone} opacity-40 group-hover:opacity-70 transition-opacity`} />
                <div className="flex items-center justify-between mb-2 relative">
                  <tile.icon className={`w-5 h-5 ${tile.tone}`} aria-hidden="true" />
                  <span className="text-[10px] text-content-tertiary font-bold tracking-wider uppercase group-hover:text-paytm-blue-action transition-colors">
                    View &rarr;
                  </span>
                </div>
                <p className="text-3xl font-extrabold text-content-primary relative tracking-tight">
                  {data[tile.key]}
                </p>
                <p className="text-xs font-bold text-content-primary mt-1 relative">
                  {tile.label}
                </p>
                <p className="text-[11px] text-content-tertiary mt-0.5 relative line-clamp-1">
                  {tile.description}
                </p>
              </Card>
            ))}
          </div>

          <div className="grid lg:grid-cols-3 gap-6 items-start">
            {/* Left Column (2 Cols): Needs Attention Urgent List */}
            <div className="lg:col-span-2 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-content-primary flex items-center gap-2">
                    <Clock className="w-5 h-5 text-paytm-blue-action" /> Needs Attention
                  </h2>
                  <p className="text-xs text-content-secondary mt-0.5">
                    Unclaimed exceptions awaiting review officer assignment.
                  </p>
                </div>
                <button
                  onClick={() => navigate('/review/queue?tab=PENDING')}
                  className="text-xs text-paytm-blue-action hover:text-paytm-blue font-bold flex items-center gap-1 transition-colors"
                >
                  View All ({data.pending_review}) <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>

              {pendingLoading ? (
                <Card className="h-48 flex items-center justify-center bg-white border border-surface-border">
                  <Spinner size="md" className="text-paytm-blue" />
                </Card>
              ) : urgentCases.length > 0 ? (
                <div className="space-y-3">
                  {urgentCases.map((c) => (
                    <Card
                      key={c.case_id}
                      onClick={() => navigate(`/review/case/${c.case_id}`)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          navigate(`/review/case/${c.case_id}`);
                        }
                      }}
                      className="p-4 sm:p-5 bg-white border border-surface-border shadow-xs hover:shadow-card hover:border-slate-300 transition-all rounded-card cursor-pointer group"
                    >
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="space-y-1.5 flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full ${
                              c.priority === 'HIGH' ? 'bg-red-50 text-red-700' : 'bg-slate-100 text-slate-700'
                            }`}>
                              {c.priority} Priority
                            </span>
                            <span className="text-xs font-mono font-semibold text-content-secondary">
                              {c.case_number}
                            </span>
                            <span className="text-xs text-content-tertiary flex items-center gap-1">
                              <Clock className="w-3 h-3" /> Waiting {formatRelativeTime(c.created_at)}
                            </span>
                          </div>
                          <h3 className="text-sm font-bold text-content-primary truncate group-hover:text-paytm-blue transition-colors">
                            {c.journey_display_name}: {c.reason_title}
                          </h3>
                          <p className="text-xs text-content-secondary line-clamp-1">
                            {c.reason_description}
                          </p>
                        </div>
                        <div className="flex flex-row sm:flex-col items-center sm:items-end justify-between sm:justify-center gap-2 shrink-0">
                          <StatusBadge status={c.status} size="sm" />
                          <Button
                            variant="primary"
                            size="sm"
                            className="sm:opacity-90 group-hover:opacity-100 transition-opacity whitespace-nowrap text-xs"
                          >
                            Review Case
                          </Button>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              ) : (
                <Card className="p-8 text-center bg-surface-subtle border border-surface-border">
                  <CheckCircle2 className="w-8 h-8 text-paytm-green mx-auto mb-3" />
                  <h3 className="text-sm font-bold text-content-primary">{"You're all caught up"}</h3>
                  <p className="text-xs text-content-secondary mt-1">
                    No cases currently require immediate triage. Check back when customers submit conflicting evidence.
                  </p>
                </Card>
              )}
            </div>

            {/* Right Column (1 Col): Active Workspace & Quick Hub */}
            <div className="space-y-6">
              {/* My In-Progress Cases */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-bold text-content-primary flex items-center gap-1.5">
                    <Eye className="w-4 h-4 text-paytm-blue" /> My Active Cases ({data.under_review})
                  </h2>
                  <button
                    onClick={() => navigate('/review/queue?tab=MINE')}
                    className="text-xs text-paytm-blue-action hover:text-paytm-blue font-semibold"
                  >
                    View &rarr;
                  </button>
                </div>

                {myLoading ? (
                  <Card className="h-32 flex items-center justify-center bg-white border border-surface-border">
                    <Spinner size="sm" className="text-paytm-blue" />
                  </Card>
                ) : activeCases.length > 0 ? (
                  <div className="space-y-2">
                    {activeCases.map((c) => (
                      <Card
                        key={c.case_id}
                        onClick={() => navigate(`/review/case/${c.case_id}`)}
                        role="button"
                        tabIndex={0}
                        className="p-3 bg-white border border-surface-border hover:border-slate-300 transition-all rounded-card cursor-pointer group"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <span className="text-[10px] font-mono text-content-tertiary block">
                              {c.case_number}
                            </span>
                            <p className="text-xs font-bold text-content-primary truncate group-hover:text-paytm-blue transition-colors">
                              {c.reason_title}
                            </p>
                          </div>
                          <span className="text-[11px] font-semibold text-paytm-blue-action shrink-0">
                            Resume &rarr;
                          </span>
                        </div>
                      </Card>
                    ))}
                  </div>
                ) : (
                  <Card className="p-4 text-center bg-white border border-surface-border">
                    <Inbox className="w-6 h-6 text-content-tertiary mx-auto mb-1.5" />
                    <p className="text-xs font-semibold text-content-primary">No cases claimed</p>
                    <p className="text-[11px] text-content-secondary mt-0.5">
                      Pick a case from Needs Attention to start reviewing.
                    </p>
                  </Card>
                )}
              </div>

              {/* Status Queues Summary */}
              <div className="space-y-3">
                <h2 className="text-sm font-bold text-content-primary">Operational Queues</h2>
                <Card className="p-3 bg-white border border-surface-border divide-y divide-surface-border">
                  <button
                    onClick={() => navigate('/review/queue?tab=WAITING')}
                    className="w-full text-left py-2.5 px-2 hover:bg-slate-50 transition-colors flex items-center justify-between rounded-sm group"
                  >
                    <div className="flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-full bg-amber-50 flex items-center justify-center shrink-0">
                        <Hourglass className="w-3.5 h-3.5 text-amber-600" />
                      </div>
                      <div>
                        <p className="text-xs font-bold text-content-primary group-hover:text-paytm-blue transition-colors">
                          Waiting on Customer
                        </p>
                        <p className="text-[10px] text-content-secondary">
                          {data.waiting_customer} cases pending information
                        </p>
                      </div>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-content-tertiary group-hover:text-paytm-blue transition-colors" />
                  </button>

                  <button
                    onClick={() => navigate('/review/queue?tab=ESCALATED')}
                    className="w-full text-left py-2.5 px-2 hover:bg-slate-50 transition-colors flex items-center justify-between rounded-sm group"
                  >
                    <div className="flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-full bg-red-50 flex items-center justify-center shrink-0">
                        <ArrowUpCircle className="w-3.5 h-3.5 text-red-600" />
                      </div>
                      <div>
                        <p className="text-xs font-bold text-content-primary group-hover:text-paytm-blue transition-colors">
                          Escalated to Specialist
                        </p>
                        <p className="text-[10px] text-content-secondary">
                          {data.escalated} cases requiring escalation handling
                        </p>
                      </div>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-content-tertiary group-hover:text-paytm-blue transition-colors" />
                  </button>

                  <button
                    onClick={() => navigate('/review/queue?tab=RESOLVED')}
                    className="w-full text-left py-2.5 px-2 hover:bg-slate-50 transition-colors flex items-center justify-between rounded-sm group"
                  >
                    <div className="flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-full bg-emerald-50 flex items-center justify-center shrink-0">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                      </div>
                      <div>
                        <p className="text-xs font-bold text-content-primary group-hover:text-paytm-blue transition-colors">
                          Resolved Today
                        </p>
                        <p className="text-[10px] text-content-secondary">
                          {data.resolved_today} completed exceptions
                        </p>
                      </div>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-content-tertiary group-hover:text-paytm-blue transition-colors" />
                  </button>
                </Card>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default ReviewDashboard;
