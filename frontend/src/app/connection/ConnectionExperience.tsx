import { useEffect, useRef, type ReactElement } from 'react';
import { FlowVisual } from './FlowVisual';
import { usePrefersReducedMotion } from './usePrefersReducedMotion';
import { useElapsedSeconds } from './useElapsedSeconds';
import {
  AMBIENT_EVENTS,
  AMBIENT_EVENT_DURATION_S,
  FAST_PATH_THRESHOLD_MS,
  MAX_EXIT_WAIT_MS,
  PHASE_ENTRANCE_MS,
  PHASE_LABELS,
  phaseForElapsedSeconds,
  phaseStartSeconds,
} from './connectionPhases';

export interface ConnectionExperienceProps {
  /** Real elapsed-time signal owned by BootGate — never a fake timer here. */
  slow: boolean;
  /**
   * True once the real backend/session is ready. The story keeps playing
   * until the *current* chapter's own entrance choreography reaches a
   * natural stopping point — never the rest of the story — at which point
   * `onReadyToExit` fires exactly once. Optional so this component still
   * works standalone (e.g. in isolated tests/stories).
   */
  backendReady?: boolean;
  /** Fires once, when it's safe to hand off to the success/exit transition. */
  onReadyToExit?: () => void;
}

/**
 * The premium first-connection experience. Purely presentational — BootGate
 * remains the sole owner of real connection state; this component only
 * reacts to the `slow`/`backendReady` signals it's handed. Internally it
 * also tracks its own elapsed mount time to choose which chapter of the
 * story to show — that clock never talks back to BootGate and never
 * represents real progress.
 *
 * The visual (FlowVisual) is the story: each chapter shows an actual system
 * transformation (a journey assembling, evidence connecting, invalid paths
 * dropping away, six journeys folding into one recovery layer, everything
 * converging back into the FLOW). This component only supplies one short
 * supporting label per chapter — it never cycles quotes on a timer.
 */
export function ConnectionExperience({ slow, backendReady = false, onReadyToExit }: ConnectionExperienceProps): ReactElement {
  const reducedMotion = usePrefersReducedMotion();
  const elapsedSeconds = useElapsedSeconds();
  const phase = phaseForElapsedSeconds(elapsedSeconds);
  const isAmbient = phase === 'ambient';

  const ambientIndex = isAmbient
    ? Math.floor((elapsedSeconds - 125) / AMBIENT_EVENT_DURATION_S) % AMBIENT_EVENTS.length
    : 0;
  const copy = isAmbient ? AMBIENT_EVENTS[ambientIndex].label : PHASE_LABELS[phase];

  const statusAnnouncement = slow ? 'Still connecting to PaytmFlow.' : 'Connecting to PaytmFlow.';

  // Real (not fake) mount timestamp — used only to work out how far into
  // the *current* chapter's own entrance we are the moment the backend
  // becomes ready, so we can let that one transition finish instead of
  // either cutting it off mid-flight or waiting for the entire remaining
  // story. `useElapsedSeconds` ticks once a second, too coarse for this.
  const mountedAtRef = useRef<number | null>(null);
  if (mountedAtRef.current === null) {
    mountedAtRef.current = Date.now();
  }
  // Guards against multiple readiness signals (or effect re-runs) ever
  // scheduling more than one exit — "only ONE navigation".
  const exitScheduledRef = useRef(false);

  useEffect(() => {
    if (!backendReady || !onReadyToExit || exitScheduledRef.current) return undefined;
    exitScheduledRef.current = true;

    const preciseElapsedMs = Date.now() - (mountedAtRef.current ?? Date.now());

    // Backend was essentially already ready when the story began (a fast/
    // warm connection) — preserve the existing short, no-artificial-delay
    // experience instead of waiting out a chapter's entrance.
    if (preciseElapsedMs < FAST_PATH_THRESHOLD_MS) {
      onReadyToExit();
      return undefined;
    }

    const currentPhase = phaseForElapsedSeconds(Math.floor(preciseElapsedMs / 1000));
    const phaseStartMs = phaseStartSeconds(currentPhase) * 1000;
    const msIntoPhase = preciseElapsedMs - phaseStartMs;
    const entranceMs = PHASE_ENTRANCE_MS[currentPhase];
    const waitMs = Math.min(Math.max(0, entranceMs - msIntoPhase), MAX_EXIT_WAIT_MS);

    if (waitMs <= 0) {
      onReadyToExit();
      return undefined;
    }
    const timer = setTimeout(onReadyToExit, waitMs);
    return () => clearTimeout(timer);
  }, [backendReady, onReadyToExit]);

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
