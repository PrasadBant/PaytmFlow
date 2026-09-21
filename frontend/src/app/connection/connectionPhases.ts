export type ConnectionPhase =
  | 'build'
  | 'assemble'
  | 'documents'
  | 'mismatch'
  | 'intelligence'
  | 'resolve'
  | 'journeys'
  | 'converge'
  | 'settle'
  | 'ambient';

// Broad narrative chapters, not a rigid countdown — the real backend response
// (via BootGate's `slow`/success signals) can interrupt any phase at any
// time. Each chapter mounts its own scene (see FlowVisual) that shows a real
// system transformation, then holds its end state until the next chapter
// replaces it. Nothing here fakes progress; it only decides which part of
// the PaytmFlow story is currently being shown while we wait.
const PHASE_START_SECONDS: Array<[ConnectionPhase, number]> = [
  ['build', 0],
  ['assemble', 8],
  ['documents', 22],
  ['mismatch', 38],
  ['intelligence', 52],
  ['resolve', 68],
  ['journeys', 82],
  ['converge', 98],
  ['settle', 112],
  ['ambient', 125],
];

export function phaseForElapsedSeconds(elapsedSeconds: number): ConnectionPhase {
  let current: ConnectionPhase = 'build';
  for (const [phase, start] of PHASE_START_SECONDS) {
    if (elapsedSeconds >= start) current = phase;
  }
  return current;
}

/** When the given chapter started, in seconds since mount. */
export function phaseStartSeconds(phase: ConnectionPhase): number {
  const entry = PHASE_START_SECONDS.find(([p]) => p === phase);
  return entry ? entry[1] : 0;
}

// How long each chapter's own entrance choreography takes to visually
// settle (its "current transition"), in ms — used only to decide how long
// to let a chapter finish before cutting to the app once the backend
// becomes ready mid-story (see ConnectionExperience). These are honest
// approximations of each chapter's real settle point; MAX_EXIT_WAIT_MS below
// caps the practical wait regardless, so a chapter whose true entrance is
// longer (assemble's travelling amount, converge's four stages) is never
// waited out in full — only "the current transition", not "the rest of the
// story".
export const PHASE_ENTRANCE_MS: Record<ConnectionPhase, number> = {
  build: 3000,
  assemble: 4400,
  documents: 3900,
  mismatch: 3400,
  intelligence: 3600,
  resolve: 2600,
  journeys: 3900,
  converge: 12000,
  settle: 1000,
  ambient: 0,
};

/** Upper bound on how long the exit can be delayed once the backend is
 * ready and the story is already mid-chapter — "finish the current
 * transition", never "wait for the rest of the story". */
export const MAX_EXIT_WAIT_MS = 2500;

/** Below this real elapsed time, the backend is treated as having been
 * ready essentially before the story began — the normal fast/no-artificial-
 * delay path applies instead of waiting out a chapter's entrance. */
export const FAST_PATH_THRESHOLD_MS = 600;

// One short supporting line per chapter — it names what the visual just
// demonstrated, it never narrates a countdown and it never repeats on an
// interval. The visual transformation carries the story; text only labels it.
export const PHASE_LABELS: Record<ConnectionPhase, string> = {
  build: 'Building the system.',
  assemble: 'A financial journey takes shape.',
  documents: 'Documents become structured information.',
  mismatch: 'Declared details meet the evidence.',
  intelligence: 'AI reads it. Rules confirm it.',
  resolve: 'Only the valid path continues.',
  journeys: 'Six journeys. One recovery layer.',
  converge: 'Everything connects back.',
  settle: 'From stuck to next step.',
  ambient: 'Still here with you.',
};

// Ambient chapter (2m+): small, independent, non-repeating-in-a-row
// conceptual events. Selected by elapsed time (not randomised) so a given
// viewer sees them in a stable, deliberate order rather than a shuffled loop.
export interface AmbientEvent {
  label: string;
}

export const AMBIENT_EVENTS: AmbientEvent[] = [
  { label: 'A document reattaches.' },
  { label: 'Evidence reconnects.' },
  { label: 'A rule check runs.' },
  { label: 'A journey node responds.' },
  { label: 'A path branches and resolves.' },
  { label: 'A reviewer briefly checks in.' },
  { label: 'The audit trail grows.' },
];

export const AMBIENT_EVENT_DURATION_S = 8;
