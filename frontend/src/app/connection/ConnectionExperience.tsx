import { useEffect, useState, type ReactElement } from 'react';
import { FlowVisual } from './FlowVisual';
import { usePrefersReducedMotion } from './usePrefersReducedMotion';
import { useElapsedSeconds } from './useElapsedSeconds';
import { AMBIENT_MESSAGES, MESSAGES, phaseForElapsedSeconds } from './connectionPhases';

export interface ConnectionExperienceProps {
  /** Real elapsed-time signal owned by BootGate — never a fake timer here. */
  slow: boolean;
}

const MESSAGE_INTERVAL_MS = 2600;
const AMBIENT_MESSAGE_INTERVAL_MS = 4600;

/**
 * The premium first-connection experience. Purely presentational — BootGate
 * remains the sole owner of real connection state; this component only
 * reacts to the `slow` signal it's handed. Internally it also tracks its own
 * elapsed mount time to choose which broad story phase to show — that clock
 * never talks back to BootGate and never represents real progress.
 */
export function ConnectionExperience({ slow }: ConnectionExperienceProps): ReactElement {
  const reducedMotion = usePrefersReducedMotion();
  const elapsedSeconds = useElapsedSeconds();
  const phase = phaseForElapsedSeconds(elapsedSeconds);
  const isAmbient = phase === 'ambient';
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    const pool = isAmbient ? AMBIENT_MESSAGES : MESSAGES;
    const interval = isAmbient ? AMBIENT_MESSAGE_INTERVAL_MS : MESSAGE_INTERVAL_MS;
    const id = setInterval(() => {
      setMessageIndex((i) => (i + 1) % pool.length);
    }, interval);
    return () => clearInterval(id);
  }, [isAmbient]);

  const pool = isAmbient ? AMBIENT_MESSAGES : MESSAGES;
  const copy = pool[messageIndex % pool.length];

  const statusAnnouncement = slow ? 'Still connecting to PaytmFlow.' : 'Connecting to PaytmFlow.';

  return (
    <div
      data-testid="boot-gate-loading"
      className="min-h-screen flex flex-col items-center justify-center px-6 py-10 text-center bg-gradient-to-b from-surface-muted to-surface overflow-hidden"
    >
      <div
        className="flex flex-col items-center gap-1 mb-8 md:mb-10 animate-pf-copy-in motion-reduce:animate-none"
        aria-hidden="true"
      >
        <span
          className={
            'font-bold text-2xl md:text-3xl tracking-tight bg-gradient-to-r from-paytm-blue via-paytm-blue-action to-paytm-blue ' +
            'bg-clip-text text-transparent bg-[length:200%_auto] ' +
            (reducedMotion ? '' : 'animate-pf-shimmer')
          }
        >
          PaytmFlow
        </span>
        <span className="text-sm text-content-tertiary">Let&apos;s get things moving.</span>
      </div>

      <FlowVisual reducedMotion={reducedMotion} phase={phase} />

      <div className="mt-8 md:mt-10 min-h-[1.5rem]">
        <p
          key={copy}
          aria-hidden="true"
          className="text-sm text-content-secondary animate-pf-copy-in motion-reduce:animate-none"
        >
          {copy}
        </p>
        <span className="sr-only" role="status" aria-live="polite">
          {statusAnnouncement}
        </span>
      </div>
    </div>
  );
}

export default ConnectionExperience;
