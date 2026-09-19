import type React from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, Circle, FileSearch } from 'lucide-react';
import { Card } from './primitives/Card';
import { Button } from './primitives/Button';
import { useJourneyReviewStatus } from '@/api/hooks/useReview';

export interface ReviewStatusCardProps {
  journeyId: string;
}

// Customer-facing surface for a Human Review case - deliberately shows only
// customer-safe phrasing (no case IDs, reviewer identity, or internal
// metadata; see backend app/schemas/review.py's CustomerReviewStatus).
export const ReviewStatusCard: React.FC<ReviewStatusCardProps> = ({ journeyId }) => {
  const navigate = useNavigate();
  const { data } = useJourneyReviewStatus(journeyId);

  if (!data || !data.has_open_case) return null;

  const waitingOnCustomer = data.status === 'ADDITIONAL_INFO_REQUIRED';
  const requestedDocs = data.requested_information?.requested_docs as string[] | undefined;

  return (
    <Card
      data-testid="review-status-card"
      padding="lg"
      className="bg-white border border-amber-200 space-y-3"
    >
      <div className="flex items-center gap-2">
        <FileSearch className="w-5 h-5 text-paytm-amber" />
        <h2 className="text-sm font-bold text-content-primary">{data.title}</h2>
      </div>
      <p className="text-sm text-content-secondary">{data.description}</p>

      <div className="space-y-1.5 pt-1">
        <StepRow label="Documents received" done />
        <StepRow label="Automated checks completed" done />
        <StepRow label="Manual verification" done={false} active />
        <StepRow label="Journey continuation" done={false} />
      </div>

      {waitingOnCustomer && requestedDocs && requestedDocs.length > 0 && (
        <div
          className="p-3 rounded-button bg-amber-50 border border-amber-200 space-y-2"
          data-testid="review-requested-info"
        >
          <p className="text-xs font-semibold text-content-primary">Action required</p>
          <p className="text-xs text-content-secondary">
            We need: {requestedDocs.join(', ')}
          </p>
          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate(`/j/${journeyId}/next`)}
          >
            Provide Additional Information
          </Button>
        </div>
      )}
    </Card>
  );
};

const StepRow: React.FC<{ label: string; done: boolean; active?: boolean }> = ({
  label,
  done,
  active,
}) => (
  <div className="flex items-center gap-2 text-xs">
    {done ? (
      <CheckCircle2 className="w-3.5 h-3.5 text-paytm-green shrink-0" />
    ) : (
      <Circle
        className={`w-3.5 h-3.5 shrink-0 ${active ? 'text-paytm-amber' : 'text-content-tertiary'}`}
      />
    )}
    <span className={done ? 'text-content-secondary' : 'text-content-tertiary'}>{label}</span>
  </div>
);

export default ReviewStatusCard;
