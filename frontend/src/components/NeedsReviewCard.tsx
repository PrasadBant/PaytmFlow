import { useState, type ReactElement } from 'react';
import { AlertCircle, HelpCircle, ArrowRight } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Button } from '@/components/primitives/Button';
import { Badge } from '@/components/primitives/Badge';
import { Input } from '@/components/primitives/Input';
import { MoneyInput } from '@/components/primitives/MoneyInput';
import { Spinner } from '@/components/primitives/Spinner';
import { useClarification, type ActionResponse } from '@/api/hooks/useClarification';
import { mapErrorToUxAction } from '@/api/errors';
import { cn } from '@/lib/utils';
import type { components } from '@/api/types.gen';

type FieldState = components['schemas']['FieldState'];

export interface NeedsReviewCardProps {
  journeyId: string;
  snapshotId: string;
  field?: FieldState | null;
  fields?: FieldState[];
  onResolved?: (response: ActionResponse) => void;
  className?: string;
}

export const NeedsReviewCard = ({
  journeyId,
  snapshotId,
  field,
  fields,
  onResolved,
  className,
}: NeedsReviewCardProps): ReactElement | null => {
  const clarificationMutation = useClarification();
  const [selectedAnswer, setSelectedAnswer] = useState<unknown>('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Exact Rule: Render exactly one question even if multiple ambiguous fields exist
  const targetField: FieldState | undefined =
    field ?? fields?.find((f) => f.status === 'AMBIGUOUS' || f.ambiguity);

  if (!targetField || !targetField.ambiguity) {
    return null;
  }

  const { ambiguity } = targetField;
  const ambiguityId = ambiguity.ambiguity_id || `${targetField.key}_CLARIFICATION`;
  const questionText = ambiguity.question || `Please clarify the value for ${targetField.label}.`;
  const reasonText = ambiguity.reason || targetField.explanation;
  const answerType = ambiguity.answer_type || 'CHOICE';
  const choices = ambiguity.choices || [];

  const isAnswerValid =
    selectedAnswer !== undefined &&
    selectedAnswer !== null &&
    String(selectedAnswer).trim() !== '';

  const handleSubmit = async (e?: React.FormEvent): Promise<void> => {
    if (e) e.preventDefault();
    if (!isAnswerValid || clarificationMutation.isPending) return;
    setErrorMessage(null);

    try {
      const response = await clarificationMutation.mutateAsync({
        journeyId,
        ambiguity_id: ambiguityId,
        field: targetField.key,
        answer: selectedAnswer,
        expected_snapshot_id: snapshotId,
      });

      if (onResolved) {
        onResolved(response);
      }
    } catch (err) {
      setErrorMessage(mapErrorToUxAction(err).message);
    }
  };

  return (
    <Card
      data-testid="needs-review-card"
      className={cn(
        'p-5 sm:p-6 bg-surface border-2 border-amber-200 shadow-card rounded-card space-y-5',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-amber-100 text-amber-800 flex items-center justify-center shrink-0">
            <HelpCircle className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <Badge variant="warning" showDefaultIcon={false} className="text-xs font-bold px-2 py-0.5">
                Review Required
              </Badge>
              <span className="text-xs text-content-tertiary font-semibold uppercase tracking-wider">
                {targetField.label}
              </span>
            </div>
            <h3 className="text-base font-bold text-content-primary mt-1" data-testid="clarification-question">
              {questionText}
            </h3>
          </div>
        </div>
      </div>

      {/* Explanation / Context */}
      {reasonText && (
        <div
          data-testid="clarification-reason"
          className="p-3.5 rounded-card bg-amber-50/70 border border-amber-200/80 text-xs text-amber-900 leading-relaxed"
        >
          <span className="font-semibold">Reason: </span>
          <span>{reasonText}</span>
        </div>
      )}

      {/* Answer Controls Based on answer_type */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <div className="text-xs font-bold uppercase tracking-wider text-content-secondary">
            Your Response
          </div>

          {/* 1. CHOICE */}
          {answerType === 'CHOICE' && choices.length > 0 && (
            <div className="space-y-2" data-testid="choices-container">
              {choices.map((choice, index) => {
                const isSelected = selectedAnswer === choice.value;
                return (
                  <button
                    key={index}
                    type="button"
                    data-testid={`clarification-choice-${index}`}
                    onClick={() => setSelectedAnswer(choice.value)}
                    className={cn(
                      'w-full text-left p-3.5 rounded-card border transition-all text-xs sm:text-sm flex items-center justify-between gap-3',
                      isSelected
                        ? 'border-paytm-blue bg-paytm-blue-50/70 text-paytm-blue font-semibold shadow-xs'
                        : 'border-surface-border bg-surface text-content-primary hover:bg-surface-subtle hover:border-slate-300'
                    )}
                  >
                    <span>{choice.label || String(choice.value)}</span>
                    <div
                      className={cn(
                        'w-4 h-4 rounded-full border flex items-center justify-center shrink-0',
                        isSelected ? 'border-paytm-blue bg-paytm-blue text-white' : 'border-slate-300'
                      )}
                    >
                      {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-white" />}
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {/* 2. MONEY */}
          {answerType === 'MONEY' && (
            <MoneyInput
              value={typeof selectedAnswer === 'number' ? selectedAnswer : ''}
              onChange={(val) => setSelectedAnswer(val)}
              placeholder="Enter confirmed amount"
              data-testid="clarification-input"
            />
          )}

          {/* 3. NUMBER */}
          {answerType === 'NUMBER' && (
            <Input
              type="number"
              value={String(selectedAnswer ?? '')}
              onChange={(e) => setSelectedAnswer(e.target.value === '' ? '' : Number(e.target.value))}
              placeholder="Enter number"
              data-testid="clarification-input"
            />
          )}

          {/* 4. TEXT */}
          {answerType === 'TEXT' && (
            <Input
              type="text"
              value={String(selectedAnswer ?? '')}
              onChange={(e) => setSelectedAnswer(e.target.value)}
              placeholder="Enter clarification details"
              data-testid="clarification-input"
            />
          )}

          {/* 5. DATE */}
          {answerType === 'DATE' && (
            <Input
              type="date"
              value={String(selectedAnswer ?? '')}
              onChange={(e) => setSelectedAnswer(e.target.value)}
              data-testid="clarification-input"
            />
          )}

          {/* 6. BOOLEAN */}
          {answerType === 'BOOLEAN' && (
            <div className="grid grid-cols-2 gap-3" data-testid="boolean-choices">
              <button
                type="button"
                data-testid="clarification-choice-true"
                onClick={() => setSelectedAnswer(true)}
                className={cn(
                  'p-3 rounded-card border text-sm font-semibold transition-all text-center',
                  selectedAnswer === true
                    ? 'border-paytm-blue bg-paytm-blue-50 text-paytm-blue'
                    : 'border-surface-border bg-surface text-content-primary hover:bg-surface-subtle'
                )}
              >
                Yes
              </button>
              <button
                type="button"
                data-testid="clarification-choice-false"
                onClick={() => setSelectedAnswer(false)}
                className={cn(
                  'p-3 rounded-card border text-sm font-semibold transition-all text-center',
                  selectedAnswer === false
                    ? 'border-paytm-blue bg-paytm-blue-50 text-paytm-blue'
                    : 'border-surface-border bg-surface text-content-primary hover:bg-surface-subtle'
                )}
              >
                No
              </button>
            </div>
          )}
        </div>

        {/* Error Alert */}
        {errorMessage && (
          <div
            data-testid="clarification-error"
            className="p-3 rounded-card bg-paytm-red-light border border-red-200 text-paytm-red text-xs flex items-center gap-2"
          >
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Action Button */}
        <div className="pt-2 flex justify-end">
          <Button
            type="submit"
            variant="primary"
            size="md"
            disabled={!isAnswerValid || clarificationMutation.isPending}
            data-testid="submit-clarification-btn"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2"
          >
            {clarificationMutation.isPending ? (
              <>
                <Spinner size="sm" className="text-white" />
                <span>Submitting Clarification...</span>
              </>
            ) : (
              <>
                <span>Submit Clarification</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </Button>
        </div>
      </form>
    </Card>
  );
};

export default NeedsReviewCard;
