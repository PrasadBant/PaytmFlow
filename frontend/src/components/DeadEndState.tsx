import type { ReactElement } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertOctagon, RotateCcw, ArrowLeft } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { cn } from '@/lib/utils';

export interface DeadEndStateProps {
  title?: string;
  message?: string;
  journeyId?: string;
  className?: string;
}

export function DeadEndState({
  title = 'No Automated Action Available',
  message = 'Based on the provided information, no further automated actions can resolve the current requirements.',
  journeyId,
  className,
}: DeadEndStateProps): ReactElement {
  const navigate = useNavigate();

  return (
    <div data-testid="dead-end-state" className={cn('max-w-2xl mx-auto p-6 md:p-8', className)}>
      <Card className="p-8 md:p-10 text-center bg-surface border-paytm-red/30 shadow-card space-y-6">
        <div className="w-14 h-14 mx-auto rounded-full bg-paytm-red-light text-paytm-red flex items-center justify-center">
          <AlertOctagon className="w-8 h-8" aria-hidden="true" />
        </div>

        <div className="space-y-2">
          <h2 className="text-xl md:text-2xl font-bold text-content-primary tracking-tight">
            {title}
          </h2>
          <p className="text-sm text-content-secondary leading-relaxed max-w-md mx-auto">
            {message}
          </p>
        </div>

        <div className="p-4 rounded-card bg-surface-subtle border border-surface-border text-xs text-content-secondary max-w-md mx-auto text-left">
          <p className="font-semibold text-content-primary mb-1">What can you do next?</p>
          <ul className="list-disc list-inside space-y-1">
            <li>Review previously uploaded evidence or verify declared parameters.</li>
            <li>Start a new journey with alternative parameters.</li>
            <li>Contact support if you believe your documents meet the requirements.</li>
          </ul>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
          {journeyId && (
            <Button variant="secondary" onClick={() => navigate(`/j/${journeyId}`)}>
              <ArrowLeft className="w-4 h-4 mr-1.5" />
              <span>Back to Status</span>
            </Button>
          )}
          <Button variant="primary" onClick={() => navigate('/start')}>
            <RotateCcw className="w-4 h-4 mr-1.5" />
            <span>Explore Other Journeys</span>
          </Button>
        </div>
      </Card>
    </div>
  );
}

export default DeadEndState;
