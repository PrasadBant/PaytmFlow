import { type ReactElement } from 'react';
import { FlowVisual } from './FlowVisual';
import { usePrefersReducedMotion } from './usePrefersReducedMotion';
import { useElapsedSeconds } from './useElapsedSeconds';
import {
  AMBIENT_EVENTS,
  AMBIENT_EVENT_DURATION_S,
  PHASE_LABELS,
  phaseForElapsedSeconds,
} from './connectionPhases';

export interface ConnectionExperienceProps {
  /** Real elapsed-time signal owned by BootGate — never a fake timer here. */
  slow: boolean;
}

/**
 * The premium first-connection experience. Purely presentational — BootGate
 * remains the sole owner of real connection state; this component only
 * reacts to the `slow` signal it's handed. Internally it also tracks its own
 * elapsed mount time to choose which chapter of the story to show — that
 * clock never talks back to BootGate and never represents real progress.
 *
 * The visual (FlowVisual) is the story: each chapter shows an actual system
 * transformation (a journey assembling, evidence connecting, invalid paths
 * dropping away, six journeys folding into one recovery layer, everything
 * converging back into the FLOW). This component only supplies one short
 * supporting label per chapter — it never cycles quotes on a timer.
 */
export function ConnectionExperience({ slow }: ConnectionExperienceProps): ReactElement {
  const reducedMotion = usePrefersReducedMotion();
  const elapsedSeconds = useElapsedSeconds();
  const phase = phaseForElapsedSeconds(elapsedSeconds);
  const isAmbient = phase === 'ambient';

  const ambientIndex = isAmbient
    ? Math.floor((elapsedSeconds - 125) / AMBIENT_EVENT_DURATION_S) % AMBIENT_EVENTS.length
    : 0;
  const copy = isAmbient ? AMBIENT_EVENTS[ambientIndex].label : PHASE_LABELS[phase];

  const statusAnnouncement = slow ? 'Still connecting to PaytmFlow.' : 'Connecting to PaytmFlow.';

  return (
    <div
      data-testid="boot-gate-loading"
      className="min-h-screen flex flex-col items-center justify-center px-6 py-10 text-center bg-gradient-to-b from-surface-muted to-surface overflow-hidden"
    >
      <div
        className="flex flex-col items-center gap-1 mb-6 md:mb-8 animate-pf-copy-in motion-reduce:animate-none"
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

      <FlowVisual reducedMotion={reducedMotion} phase={phase} ambientIndex={ambientIndex} ambientLabel={copy} />

      <div className="mt-6 md:mt-8 min-h-[1.5rem]">
        <p
          key={isAmbient ? `ambient-${ambientIndex}` : phase}
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
