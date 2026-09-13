import type { ReactElement } from 'react';
import { Bot } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { cn } from '@/lib/utils';

export interface AssistantHelpCardProps {
  title?: string;
  description?: string;
  tips?: string[];
  onAskNow?: () => void;
  className?: string;
}

export function AssistantHelpCard({
  title = 'Need help?',
  description = 'Ask our AI Assistant for guidance.',
  tips = [],
  onAskNow,
  className,
}: AssistantHelpCardProps): ReactElement {
  return (
    <Card
      data-testid="assistant-help-card"
      className={cn('p-6 space-y-4 text-center rounded-card bg-white border border-surface-border shadow-xs flex flex-col items-center justify-center', className)}
    >
      <div className="w-14 h-14 rounded-full bg-blue-50 text-paytm-blue-action flex items-center justify-center">
        <Bot className="w-7 h-7" aria-hidden="true" />
      </div>

      <div className="space-y-1">
        <h3 className="text-base font-bold text-content-primary">
          {title}
          <span className="sr-only">Need Help with this Step?</span>
        </h3>
        <p className="text-xs sm:text-sm text-content-secondary leading-relaxed max-w-xs">
          {description}
        </p>
      </div>

      {tips.length > 0 && (
        <ul className="text-xs text-content-secondary space-y-1 text-left w-full pl-2">
          {tips.map((tip, idx) => (
            <li key={idx} className="list-disc list-inside">
              {tip}
            </li>
          ))}
        </ul>
      )}

      <Button
        variant="outline"
        size="sm"
        className="w-full sm:w-auto px-6 py-2 text-xs font-bold"
        onClick={onAskNow}
      >
        Ask Now
      </Button>
    </Card>
  );
}

export default AssistantHelpCard;
