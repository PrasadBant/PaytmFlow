import { AlertCircle, AlertTriangle, CheckCircle2 } from 'lucide-react';
import type { ReactElement } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { Card } from '@/components/primitives/Card';
import type { components } from '@/api/types.gen';

export type FieldState = components['schemas']['FieldState'];

export interface BlockerCardProps {
  field: FieldState;
  onResolve?: (resolveActionId: string, field: FieldState) => void;
  resolveHref?: string;
  className?: string;
}

export function BlockerCard({
  field,
  onResolve,
  resolveHref,
  className,
}: BlockerCardProps): ReactElement {
  const navigate = useNavigate();
  const isSatisfied = field.status === 'SATISFIED';
  const isBlocked = field.status === 'BLOCKED';
  const isAmbiguous = field.status === 'AMBIGUOUS';
  const hasResolveAction = Boolean(field.resolve_action_id) && !isSatisfied;
  // A BLOCKED field the server marked non-mandatory (field.mandatory === false) is a
  // softer blocker than a mandatory one - reflect that with amber instead of red so
  // severity is visible at a glance, same as the reference design. Never invented:
  // `mandatory` is a real FieldState field, not a derived/hardcoded distinction.
  const isSoftBlocked = isBlocked && field.mandatory === false;

  const handleResolveClick = () => {
    if (field.resolve_action_id) {
      onResolve?.(field.resolve_action_id, field);
    }
    if (resolveHref) {
      navigate(resolveHref);
    }
  };

  return (
    <Card
      data-testid={`blocker-card-${field.key}`}
      className={cn(
        'p-4 md:p-5 flex items-center justify-between gap-4 transition-all duration-150 rounded-card bg-white border border-surface-border shadow-xs hover:shadow-card',
        className
      )}
    >
      <div className="flex items-start gap-3.5 min-w-0">
        {/* Left Status Icon */}
        <div className="shrink-0 mt-0.5">
          {isBlocked && (
            <div
              className={cn(
                'w-8 h-8 rounded-full flex items-center justify-center',
                isSoftBlocked ? 'bg-amber-50 text-paytm-amber' : 'bg-red-50 text-paytm-red'
              )}
            >
              <AlertCircle className="w-5 h-5" />
              <span className="sr-only">{isSoftBlocked ? 'Blocked (optional)' : 'Blocked'}</span>
            </div>
          )}
          {isAmbiguous && (
            <div className="w-8 h-8 rounded-full bg-amber-50 text-paytm-amber flex items-center justify-center">
              <AlertTriangle className="w-5 h-5" />
              <span className="sr-only">Needs Review</span>
            </div>
          )}
          {isSatisfied && (
            <div className="w-8 h-8 rounded-full bg-emerald-50 text-paytm-green flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5" />
              <span className="sr-only">Satisfied</span>
            </div>
          )}
        </div>

        {/* Content */}
        <div className="space-y-0.5 min-w-0">
          <h3 className="text-sm md:text-base font-bold text-content-primary">
            {field.label}
          </h3>

          {field.explanation ? (
            <div className="space-y-0.5">
              <p className="text-xs sm:text-sm text-content-secondary leading-relaxed">
                {field.explanation}
              </p>
              {field.display_value && (
                <p className="text-xs text-content-secondary">
                  Value: <span className="text-content-primary font-medium">{field.display_value}</span>
                </p>
              )}
            </div>
          ) : field.display_value ? (
            <p className="text-xs text-content-secondary">
              Value: <span className="text-content-primary font-medium">{field.display_value}</span>
            </p>
          ) : null}
        </div>
      </div>

      {/* Right Resolve Action Link */}
      {hasResolveAction && (
        <div className="shrink-0 pl-2">
          {resolveHref ? (
            <Link
              to={resolveHref}
              aria-label={`Resolve ${field.label}`}
              onClick={() => field.resolve_action_id && onResolve?.(field.resolve_action_id, field)}
              className="text-paytm-blue-action hover:text-paytm-blue-action-hover font-bold text-sm inline-flex items-center gap-1 group py-1 px-2 rounded-md hover:bg-blue-50 transition-colors"
            >
              <span>Resolve →</span>
            </Link>
          ) : (
            <button
              type="button"
              aria-label={`Resolve ${field.label}`}
              onClick={handleResolveClick}
              className="text-paytm-blue-action hover:text-paytm-blue-action-hover font-bold text-sm inline-flex items-center gap-1 group py-1 px-2 rounded-md hover:bg-blue-50 transition-colors"
            >
              <span>Resolve →</span>
            </button>
          )}
        </div>
      )}
    </Card>
  );
}

export default BlockerCard;
