import { useEffect, useRef, useState, type ReactElement } from 'react';
import { FlowVisual } from './FlowVisual';
import { usePrefersReducedMotion } from './usePrefersReducedMotion';

export interface ConnectionExperienceProps {
  /** Real elapsed-time signal owned by BootGate — never a fake timer here. */
  slow: boolean;
}

const BASE_MESSAGES = [
  'Putting the pieces together…',
  'Almost ready…',
  'Good things take a moment.',
  'Ready when you are.',
];

const MESSAGE_INTERVAL_MS = 2600;
const LONG_WAIT_JOKE_DELAY_MS = 6000;

/**
 * The premium first-connection experience. Purely presentational — BootGate
 * remains the sole owner of real connection state; this component only
 * reacts to the `slow` signal it's handed.
 */
export function ConnectionExperience({ slow }: ConnectionExperienceProps): ReactElement {
  const reducedMotion = usePrefersReducedMotion();
  const [messageIndex, setMessageIndex] = useState(0);
  const [longWaitJokeShown, setLongWaitJokeShown] = useState(false);
  const longWaitStarted = useRef(false);

  useEffect(() => {
    if (slow) return undefined;
    const id = setInterval(() => {
      setMessageIndex((i) => (i + 1) % BASE_MESSAGES.length);
    }, MESSAGE_INTERVAL_MS);
    return () => clearInterval(id);
  }, [slow]);

  useEffect(() => {
    if (!slow || longWaitStarted.current) return undefined;
    longWaitStarted.current = true;
    const timer = setTimeout(() => setLongWaitJokeShown(true), LONG_WAIT_JOKE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [slow]);

  const copy = slow
    ? longWaitJokeShown
      ? "We promise we're not making you fill another form. 😄"
      : 'Still getting things ready…'
    : BASE_MESSAGES[messageIndex];

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
        <span className="font-bold text-2xl md:text-3xl tracking-tight bg-gradient-to-r from-paytm-blue to-paytm-blue-action bg-clip-text text-transparent">
          PaytmFlow
        </span>
        <span className="text-sm text-content-tertiary">Let&apos;s get things moving.</span>
      </div>

      <FlowVisual reducedMotion={reducedMotion} />

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
