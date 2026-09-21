import { useEffect, type ReactElement } from 'react';
import { Check } from 'lucide-react';
import { usePrefersReducedMotion } from './usePrefersReducedMotion';

export interface ConnectionSuccessTransitionProps {
  onComplete: () => void;
}

const STAGES = ['Explore', 'Understand', 'Recover', 'Complete'];

// A short, fixed-duration cosmetic flourish shown AFTER the real connection
// has already succeeded — never a gate on when the app becomes usable. Kept
// well under the default RTL findBy timeout (1000ms) so it never turns into
// a perceptible artificial wait. Skipped entirely under reduced motion.
export const SUCCESS_HOLD_MS = 480;

/**
 * Renders once, real connection state already resolved. Owns none of the
 * boot/retry logic — purely a presentational bridge into the real app.
 */
export function ConnectionSuccessTransition({ onComplete }: ConnectionSuccessTransitionProps): ReactElement {
  const reducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    const timer = setTimeout(onComplete, reducedMotion ? 0 : SUCCESS_HOLD_MS);
    return () => clearTimeout(timer);
  }, [onComplete, reducedMotion]);

  return (
    <div
      data-testid="boot-gate-success"
      role="status"
      aria-live="polite"
      className="min-h-screen flex flex-col items-center justify-center px-6 py-10 text-center animate-pf-copy-in motion-reduce:animate-none"
    >
      <span className="font-bold text-2xl md:text-3xl tracking-tight bg-gradient-to-r from-paytm-blue to-paytm-blue-action bg-clip-text text-transparent mb-6">
        PaytmFlow
      </span>

      <div className="flex items-center gap-2.5 md:gap-3 mb-6 flex-wrap justify-center" aria-hidden="true">
        {STAGES.map((stage, i) => (
          <span
            key={stage}
            style={{ animationDelay: `${i * 80}ms` }}
            className="inline-flex items-center gap-1 text-xs font-semibold text-paytm-green-dark bg-paytm-green-light rounded-full px-2.5 py-1 animate-pf-copy-in motion-reduce:animate-none"
          >
            <Check className="w-3 h-3" aria-hidden="true" />
            {stage}
          </span>
        ))}
      </div>

      <p
        style={{ animationDelay: '340ms' }}
        className="text-base font-semibold text-content-primary animate-pf-copy-in motion-reduce:animate-none"
      >
        Everything&apos;s ready. ✨
      </p>
      <p
        style={{ animationDelay: '380ms' }}
        className="text-sm text-content-secondary mt-1 animate-pf-copy-in motion-reduce:animate-none"
      >
        Let&apos;s simplify your financial journey.
      </p>
    </div>
  );
}

export default ConnectionSuccessTransition;
