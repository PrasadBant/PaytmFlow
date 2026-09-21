export type ConnectionPhase = 'intro' | 'discovery' | 'recovery' | 'journeys' | 'reassembly' | 'ambient';

// Broad experience phases, not a rigid countdown — the real backend response
// (via BootGate's `slow`/success signals) can interrupt any phase at any
// time. These only decide which story beat the visuals/copy are currently
// telling while we wait.
const PHASE_START_SECONDS: Array<[ConnectionPhase, number]> = [
  ['intro', 0],
  ['discovery', 10],
  ['recovery', 30],
  ['journeys', 60],
  ['reassembly', 90],
  ['ambient', 120],
];

export function phaseForElapsedSeconds(elapsedSeconds: number): ConnectionPhase {
  let current: ConnectionPhase = 'intro';
  for (const [phase, start] of PHASE_START_SECONDS) {
    if (elapsedSeconds >= start) current = phase;
  }
  return current;
}

// A deliberately curated set — long enough that a viewer waiting the full
// ~2 minutes almost never sees a line twice, but never randomly shuffled
// (that reads as glitchy, not calm).
export const MESSAGES: string[] = [
  'Getting your journey ready…',
  'Connecting the pieces…',
  'Clearing the path ahead…',
  'Finding the next step…',
  'Making complexity simpler…',
  'Organizing every step…',
  'Lining up what comes next…',
  'Bringing the journey together…',
  'One step at a time.',
  'Every journey has a next step.',
  'Turning uncertainty into action.',
  'Making the next step easier.',
  'One journey. One flow.',
  'Keeping the path clear.',
  'Everything in its place.',
  'Finding a clearer path forward.',
  'Helping you move forward.',
  'From stuck to next step.',
  'A blocked path isn’t a dead end.',
  'There’s always another way through.',
  'Six journeys. One place.',
  'Lending, insurance, credit, and more — together.',
  'Every journey, one flow.',
  'Making financial journeys simpler.',
  'Clarity when you need it.',
  'Good things take a moment.',
  'Still getting things ready…',
  'Almost ready…',
  'Thanks for hanging in there.',
  'Ready when you are.',
  'We’re still here.',
  'Taking a little extra care.',
  'Some journeys take a moment longer.',
  'Worth the wait.',
  'Nearly there.',
];

export const AMBIENT_MESSAGES: string[] = [
  'Still here with you.',
  'Good things take a moment.',
  'Taking a little extra care.',
  'Almost ready…',
  'Thanks for your patience.',
  'Ready when you are.',
];
