import type { ReactElement } from 'react';
import { Bot } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { cn } from '@/lib/utils';
import { useUiStore } from '@/state/ui';

export interface AssistantHelpCardProps {
  title?: string;
  description?: string;
  tips?: string[];
  onAskNow?: () => void;
  className?: string;
}

export function AssistantHelpCard({
  title = 'Need help?',
  description = 'Ask our AI assistant for guidance.',
  tips = [],
  onAskNow,
  className,
}: AssistantHelpCardProps): ReactElement {
  const openAssistant = useUiStore((state) => state.openAssistant);
  const handleAsk = onAskNow || (() => openAssistant());
  return (
    <Card
      data-testid="assistant-help-card"
      className={cn(
        'p-5 space-y-4 rounded-card bg-paytm-blue-50 border border-paytm-blue/10',
        className
      )}
    >
      {/* Horizontal icon + copy row, matching the reference layout */}
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-full bg-white text-paytm-blue-action flex items-center justify-center shrink-0 shadow-xs">
          <Bot className="w-6 h-6" aria-hidden="true" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-content-primary">
            {title}
            <span className="sr-only">Need Help with this Step?</span>
          </h3>
          <p className="text-xs text-content-secondary leading-relaxed">
            {description}
          </p>
        </div>
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
        className="w-full font-bold"
        onClick={handleAsk}
        data-testid="assistant-ask-now-btn"
      >
        Ask Now
      </Button>
    </Card>
  );
}

export default AssistantHelpCard;
