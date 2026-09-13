import { useState, type ReactElement } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Sparkles, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react';
import { usePack } from '@/api/hooks/usePack';
import { useCreateJourney } from '@/api/hooks/useCreateJourney';
import { SchemaForm } from '@/components/SchemaForm';
import { Card } from '@/components/primitives/Card';
import { Spinner } from '@/components/primitives/Spinner';
import { Button } from '@/components/primitives/Button';
import { ApiError } from '@/api/errors';
import type { components } from '@/api/types.gen';

type JourneyType = components['schemas']['JourneyType'];

export function Screen03GoalBasicInfo(): ReactElement {
  const { type } = useParams<{ type: string }>();
  const navigate = useNavigate();
  const normalizedType = (type || '').toUpperCase() as JourneyType;

  const { data: pack, isLoading, error, refetch } = usePack(normalizedType);
  const createJourney = useCreateJourney();

  const [naturalLanguage, setNaturalLanguage] = useState('');
  const [isNlOpen, setIsNlOpen] = useState(false);
  const [serverErrors, setServerErrors] = useState<Record<string, string> | undefined>(undefined);
  const [formError, setFormError] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div data-testid="screen-03-loading" className="flex flex-col items-center justify-center min-h-[50vh] p-8">
        <Spinner size="lg" className="text-paytm-blue mb-4" />
        <p className="text-sm font-medium text-content-secondary">Loading journey parameters...</p>
      </div>
    );
  }

  if (error || !pack) {
    return (
      <div data-testid="screen-03-error" className="max-w-page mx-auto p-6 md:p-8">
        <Link
          to="/start"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-paytm-blue hover:text-paytm-navy mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Journeys
        </Link>
        <Card className="p-8 text-center max-w-lg mx-auto">
          <AlertCircle className="w-10 h-10 text-paytm-red mx-auto mb-3" />
          <h2 className="text-lg font-bold text-content-primary mb-2">Unable to Load Journey</h2>
          <p className="text-sm text-content-secondary mb-6">
            The requested journey configuration could not be loaded.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Button variant="secondary" onClick={() => navigate('/start')}>
              Select Another Journey
            </Button>
            <Button variant="primary" onClick={() => refetch()}>
              Try Again
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const heading = 'Tell us about your goal';
  const subtext = 'This helps us personalize your recovery journey.';

  const handleFormSubmit = async (values: Record<string, unknown>): Promise<void> => {
    setFormError(null);
    setServerErrors(undefined);

    try {
      const result = await createJourney.mutateAsync({
        journey_type: pack.journey_type,
        goal: values,
        natural_language: naturalLanguage.trim() ? naturalLanguage.trim() : undefined,
      });

      navigate(`/j/${result.journey_id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'VALIDATION_ERROR' && err.details) {
          const fieldErrors: Record<string, string> = {};
          Object.entries(err.details).forEach(([k, v]) => {
            fieldErrors[k] = typeof v === 'string' ? v : JSON.stringify(v);
          });
          setServerErrors(fieldErrors);
        } else {
          setFormError(err.message || 'Failed to start journey. Please check your inputs and try again.');
        }
      } else {
        setFormError('An unexpected error occurred. Please try again.');
      }
    }
  };

  // Provide initial reference values if lending pack
  const defaultGoalValues =
    pack.journey_type === 'LENDING'
      ? {
          loan_amount: 500000,
          purpose: 'home_renovation',
          desired_tenure_months: 36,
          intent: 'new_loan',
        }
      : undefined;

  return (
    <div data-testid="screen-03-goal-basic-info" className="max-w-xl mx-auto px-4 py-8 md:py-10 space-y-6">
      {/* Back Link */}
      <div>
        <Link
          to="/start"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-paytm-blue hover:text-paytm-blue-action transition-colors group"
        >
          <ArrowLeft className="w-4 h-4 transition-transform group-hover:-translate-x-1" />
          Back
        </Link>
      </div>

      {/* Header section */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-content-primary tracking-tight">
          {heading}
        </h1>
        <p className="mt-1.5 text-sm text-content-secondary leading-relaxed">
          {subtext}
        </p>
        <span className="sr-only">{(pack as { title?: string }).title || pack.display_name}</span>
        {pack.ui_labels?.goal_heading && <span className="sr-only">{pack.ui_labels.goal_heading}</span>}
        {pack.ui_labels?.goal_subtext && <span className="sr-only">{pack.ui_labels.goal_subtext}</span>}
      </div>

      {formError && (
        <div className="p-4 rounded-card bg-paytm-red/10 border border-paytm-red/20 text-paytm-red text-sm flex items-start gap-3">
          <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Unable to continue</p>
            <p className="mt-0.5 text-xs text-paytm-red/90">{formError}</p>
          </div>
        </div>
      )}

      {/* Goal Form Card */}
      <Card className="p-6 md:p-8 shadow-xs border border-surface-border bg-white rounded-card">
        {/* Optional Natural Language Progressive Disclosure */}
        <div className="mb-6 border-b border-surface-border pb-6">
          <button
            type="button"
            onClick={() => setIsNlOpen(!isNlOpen)}
            className="flex items-center justify-between w-full text-left py-2 group text-sm font-semibold text-paytm-blue hover:text-paytm-navy transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-paytm-cyan rounded-button"
            aria-expanded={isNlOpen}
            aria-controls="nl-input-section"
          >
            <span className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-paytm-blue" />
              <span>Describe in your own words (Optional)</span>
            </span>
            {isNlOpen ? (
              <ChevronUp className="w-4 h-4 text-content-secondary" />
            ) : (
              <ChevronDown className="w-4 h-4 text-content-secondary" />
            )}
          </button>

          {isNlOpen && (
            <div id="nl-input-section" className="mt-3 space-y-2">
              <label htmlFor="natural-language-input" className="block text-xs text-content-secondary">
                Add any additional context or describe your goal in natural language.
              </label>
              <textarea
                id="natural-language-input"
                rows={3}
                value={naturalLanguage}
                onChange={(e) => setNaturalLanguage(e.target.value)}
                placeholder="e.g. Need a 5 lakh loan for home renovation, monthly salary is 85000..."
                className="w-full rounded-button bg-surface border border-surface-border p-3 text-sm text-content-primary placeholder:text-content-tertiary focus-visible:ring-2 focus-visible:ring-paytm-cyan focus-visible:border-paytm-cyan focus-visible:outline-none transition-colors duration-150 resize-none"
              />
            </div>
          )}
        </div>

        {/* Structured Schema Form */}
        <SchemaForm
          schema={pack.goal_schema}
          defaultValues={defaultGoalValues}
          submitLabel="Continue →"
          onSubmit={handleFormSubmit}
          isSubmitting={createJourney.isPending}
          serverErrors={serverErrors}
        />
      </Card>
    </div>
  );
}

export default Screen03GoalBasicInfo;
