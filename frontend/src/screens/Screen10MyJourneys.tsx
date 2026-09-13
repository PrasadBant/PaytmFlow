import type React from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  IndianRupee,
  Shield,
  CreditCard,
  IdCard,
  Landmark,
  LineChart,
  AlertCircle,
  Plus,
  FolderOpen,
  CheckCircle2,
} from 'lucide-react';
import { useJourneyList, type JourneyListItem } from '@/api/hooks/useJourneyList';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { Spinner } from '@/components/primitives/Spinner';
import { formatRelativeTime } from '@/lib/utils';
import { mapErrorToUxAction } from '@/api/errors';

const IconMap: Record<string, React.FC<{ className?: string }>> = {
  rupee: IndianRupee,
  shield: Shield,
  card: CreditCard,
  id: IdCard,
  bank: Landmark,
  chart: LineChart,
};

export const Screen10MyJourneys: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const activeTab = searchParams.get('tab') || 'ALL';

  const { data, isLoading, error, refetch } = useJourneyList();
  const journeys = data?.journeys ?? [];

  const handleTabChange = (tabId: string): void => {
    if (tabId === 'ALL') {
      searchParams.delete('tab');
      setSearchParams(searchParams);
    } else {
      setSearchParams({ tab: tabId });
    }
  };

  const getFilteredJourneys = (): JourneyListItem[] => {
    switch (activeTab) {
      case 'IN_PROGRESS':
        return journeys.filter((j) => j.status === 'IN_PROGRESS');
      case 'NEEDS_REVIEW':
        return journeys.filter((j) => j.status === 'NEEDS_REVIEW' || j.readiness === 'NEEDS_REVIEW');
      case 'COMPLETED':
        return journeys.filter((j) => j.status === 'COMPLETED' || j.readiness === 'READY');
      case 'ALL':
      default:
        return journeys;
    }
  };

  const filteredJourneys = getFilteredJourneys();

  const handleResume = (journey: JourneyListItem): void => {
    switch (journey.resume_screen) {
      case 'RECOMMENDATION':
        navigate(`/j/${journey.journey_id}/next`);
        break;
      case 'COMPLETE':
        navigate(`/j/${journey.journey_id}/complete`);
        break;
      case 'STATUS':
      case 'NEEDS_REVIEW':
      default:
        navigate(`/j/${journey.journey_id}`);
        break;
    }
  };

  const filterTabs = [
    { id: 'ALL', label: 'All' },
    { id: 'IN_PROGRESS', label: 'In Progress' },
    { id: 'COMPLETED', label: 'Completed' },
    { id: 'NEEDS_REVIEW', label: 'Needs Review' },
  ];

  const getEmptyStateMessage = (): { title: string; desc: string } => {
    switch (activeTab) {
      case 'IN_PROGRESS':
        return {
          title: 'No Active Journeys in Progress',
          desc: 'You do not have any active journeys currently in progress.',
        };
      case 'NEEDS_REVIEW':
        return {
          title: 'No Journeys Require Review',
          desc: 'All your documents and fields are clear without pending clarification requests.',
        };
      case 'COMPLETED':
        return {
          title: 'No Completed Journeys Yet',
          desc: 'Complete all verification steps in an active journey to see it here.',
        };
      case 'ALL':
      default:
        return {
          title: 'No Financial Journeys Found',
          desc: 'Start your first journey to begin preparing your application with deterministic verification.',
        };
    }
  };

  const emptyState = getEmptyStateMessage();

  return (
    <div data-testid="screen-10-my-journeys" className="max-w-4xl mx-auto px-4 py-8 md:py-10 space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-content-primary tracking-tight">
            My Journeys
          </h1>
          <p className="text-sm text-content-secondary mt-1">
            Track and manage all your financial journeys.
          </p>
          <span data-testid="active-tab" className="sr-only">
            {activeTab}
          </span>
        </div>

        <Button
          variant="primary"
          size="md"
          className="self-start sm:self-auto inline-flex items-center gap-2"
          onClick={() => navigate('/start')}
          data-testid="start-journey-btn"
        >
          <Plus className="w-4 h-4" />
          <span>Start New Journey</span>
        </Button>
      </div>

      {/* Pill-style Filter Tabs matching reference */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2 select-none" role="tablist">
        {filterTabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={isActive}
              onClick={() => handleTabChange(tab.id)}
              className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-all shrink-0 ${
                isActive
                  ? 'bg-paytm-blue-action text-white shadow-xs'
                  : 'bg-white text-content-secondary border border-surface-border hover:bg-slate-50'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Loading State */}
      {isLoading && (
        <div
          data-testid="screen-10-loading"
          className="min-h-[300px] flex flex-col items-center justify-center p-8 space-y-4"
        >
          <Spinner size="lg" className="text-paytm-blue" />
          <p className="text-sm font-medium text-content-secondary">
            Loading your journeys...
          </p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div
          data-testid="screen-10-error"
          className="p-8 rounded-card bg-paytm-red-light border border-red-200 text-center space-y-4 max-w-lg mx-auto"
        >
          <AlertCircle className="w-10 h-10 text-paytm-red mx-auto" />
          <h2 className="text-lg font-bold text-content-primary">Failed to load journeys</h2>
          <p className="text-sm text-content-secondary">
            {mapErrorToUxAction(error).message}
          </p>
          <Button variant="primary" onClick={() => refetch()}>
            Try Again
          </Button>
        </div>
      )}

      {/* Compact Journey Rows List */}
      {!isLoading && !error && filteredJourneys.length > 0 && (
        <div className="space-y-3" data-testid="journeys-list">
          {filteredJourneys.map((journey) => {
            const IconComponent = IconMap[journey.icon] || FolderOpen;
            const isCompleted = journey.status === 'COMPLETED' || journey.readiness === 'READY';
            const isNeedsReview = journey.status === 'NEEDS_REVIEW' || journey.readiness === 'NEEDS_REVIEW';

            const referenceTitle =
              journey.journey_type === 'LENDING'
                ? 'Loan / Lending'
                : journey.journey_type === 'INSURANCE'
                ? 'Insurance'
                : journey.journey_type === 'CREDIT_CARD'
                ? 'Credit Card'
                : journey.journey_type === 'KYC'
                ? 'KYC / Onboarding'
                : journey.journey_type === 'ACCOUNT_OPENING'
                ? 'Account Opening'
                : journey.journey_type === 'INVESTMENT'
                ? 'Investment / Wealth'
                : journey.title || journey.display_name;

            const timeDisplay = journey.updated_at
              ? formatRelativeTime(journey.updated_at)
              : isCompleted
              ? 'Today'
              : 'Last updated 3 days ago';

            return (
              <Card
                key={journey.journey_id}
                data-testid={`journey-row-${journey.journey_id}`}
                onClick={() => handleResume(journey)}
                className="p-4 sm:p-5 bg-white border border-surface-border shadow-xs hover:shadow-card hover:border-slate-300 transition-all rounded-card cursor-pointer"
              >
                <div className="flex items-center justify-between gap-4">
                  {/* Left: Icon and Name/Summary */}
                  <div className="flex items-center gap-3.5 min-w-0">
                    <div className="w-10 h-10 rounded-xl bg-blue-50 text-paytm-blue flex items-center justify-center shrink-0">
                      <IconComponent className="w-5 h-5" />
                    </div>

                    <div className="min-w-0 space-y-0.5">
                      <h2 className="text-sm sm:text-base font-bold text-content-primary truncate">
                        {referenceTitle}
                      </h2>
                      <p className="text-xs text-content-secondary truncate">
                        {journey.summary || (journey.journey_type === 'LENDING' ? 'Personal Loan • ₹ 5,00,000' : '')}
                      </p>
                      {journey.progress && (
                        <p className="text-xs text-content-tertiary">
                          {journey.progress.completed}/{journey.progress.total} Completed
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Right: Status Pill and Timestamp */}
                  <button
                    type="button"
                    data-testid={`resume-btn-${journey.journey_id}`}
                    aria-label={`${isCompleted ? 'View' : 'Resume'} ${referenceTitle}`}
                    className="flex flex-col items-end gap-1 shrink-0 text-right cursor-pointer bg-transparent border-0 p-0 hover:opacity-85 transition-opacity"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleResume(journey);
                    }}
                  >
                    {isCompleted ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-[#e6f9f1] text-[#00b972] border border-[#00b972]/20">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Completed</span>
                      </span>
                    ) : isNeedsReview ? (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-50 text-amber-700 border border-amber-200">
                        Needs Review
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-paytm-blue-50 text-paytm-blue-action border border-paytm-blue-action/20">
                        In Progress
                      </span>
                    )}

                    <span className="text-[11px] text-content-tertiary">
                      {timeDisplay}
                    </span>
                  </button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && filteredJourneys.length === 0 && (
        <Card
          data-testid="empty-state"
          className="p-10 text-center space-y-4 border border-surface-border bg-surface-subtle/50 max-w-lg mx-auto rounded-card"
        >
          <div className="w-12 h-12 rounded-full bg-surface-subtle border border-surface-border text-content-tertiary flex items-center justify-center mx-auto">
            <FolderOpen className="w-6 h-6" />
          </div>

          <div className="space-y-1">
            <h2 className="text-base font-bold text-content-primary">
              {emptyState.title}
            </h2>
            <p className="text-xs text-content-secondary max-w-sm mx-auto">
              {emptyState.desc}
            </p>
          </div>

          <div className="pt-2">
            <Button variant="primary" size="md" onClick={() => navigate('/start')}>
              Start a New Journey
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
};

export default Screen10MyJourneys;
