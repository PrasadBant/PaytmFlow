import type React from 'react';
import { Sparkles, AlertCircle } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { Spinner } from '@/components/primitives/Spinner';
import { mapErrorToUxAction } from '@/api/errors';
import { useSummarizeCase } from '@/api/hooks/useReview';

interface AiEvidenceSummaryProps {
  caseId: string;
}

// Advisory-only "AI Evidence Summary" (spec: reviewer AI summary). Explicit
// click, never auto-run - the reviewer decides when to request it, and the
// disclaimer the backend returns is always shown alongside the text, never
// presented as a decision or recommendation.
export const AiEvidenceSummary: React.FC<AiEvidenceSummaryProps> = ({ caseId }) => {
  const summarize = useSummarizeCase();

  return (
    <Card
      padding="lg"
      className="bg-indigo-50/30 border border-indigo-100 shadow-xs space-y-3"
      data-testid="ai-evidence-summary"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-indigo-600" />
          <h2 className="text-sm font-extrabold text-content-primary tracking-tight">
            AI Evidence Summary
          </h2>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => summarize.mutate({ caseId })}
          isLoading={summarize.isPending}
          data-testid="generate-ai-summary-btn"
        >
          {summarize.data ? 'Regenerate' : 'Generate Summary'}
        </Button>
      </div>

      {summarize.isError && (
        <div className="p-3 bg-red-50 text-paytm-red text-xs font-semibold rounded-button border border-red-200 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{mapErrorToUxAction(summarize.error).message}</span>
        </div>
      )}

      {summarize.isPending && (
        <div className="flex items-center gap-2 text-xs text-content-secondary">
          <Spinner size="sm" /> Generating advisory summary...
        </div>
      )}

      {summarize.data && (
        <div className="space-y-2">
          <p className="text-sm text-content-primary leading-relaxed bg-white p-3 rounded-button border border-indigo-100">
            {summarize.data.summary}
          </p>
          <p className="text-[11px] text-content-tertiary italic">{summarize.data.disclaimer}</p>
        </div>
      )}

      {!summarize.data && !summarize.isPending && !summarize.isError && (
        <p className="text-xs text-content-tertiary">
          Generate a plain-language recap of this case&apos;s declared value, submitted evidence,
          and system status. Advisory only - it does not change the case.
        </p>
      )}
    </Card>
  );
};

export default AiEvidenceSummary;
