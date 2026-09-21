import type { CSSProperties, ReactElement, ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { ConnectionPhase } from './connectionPhases';

export interface FlowVisualProps {
  reducedMotion: boolean;
  phase: ConnectionPhase;
  /** Which ambient micro-event is currently showing (only used when phase === 'ambient'). */
  ambientIndex?: number;
  ambientLabel?: string;
}

const STAGES = ['Explore', 'Understand', 'Recover', 'Complete'];

// A flat, deliberately understated strip — this is the "spine" the whole
// story eventually collapses into (Scene 18), so it stays present and calm
// throughout rather than competing with whichever chapter is active above it.
const STRIP_PATH_D = 'M 16 24 C 130 4, 270 4, 384 24';
const STRIP_STAGE_X = [16, 138.7, 261.3, 384];

// Which spine stage is "live" for a given chapter — the FLOW strip is not
// decorative: it visibly tracks which part of the story is currently active.
const ACTIVE_STAGE: Record<ConnectionPhase, number | null> = {
  build: null,
  assemble: 0,
  documents: 0,
  mismatch: 1,
  intelligence: 1,
  resolve: 2,
  journeys: 2,
  converge: 3,
  settle: 3,
  ambient: 3,
};

type ChipTone = 'default' | 'muted' | 'strong' | 'amber';

function chipToneClass(tone: ChipTone): string {
  switch (tone) {
    case 'strong':
      return 'bg-paytm-blue-action text-white border-paytm-blue-action shadow-sm';
    case 'amber':
      return 'bg-amber-50 text-amber-700 border-amber-300';
    case 'muted':
      return 'bg-white/70 text-content-tertiary border-surface-border';
    default:
      return 'bg-white/90 text-content-secondary border-surface-border';
  }
}

interface ChipProps {
  label: string;
  style: CSSProperties;
  className: string;
  tone?: ChipTone;
}

// Horizontally centered on its `left` coordinate — every animation class
// applied to a Chip bakes `translateX(-50%)` into its own keyframes so the
// centering survives whichever one-shot animation is currently driving it.
function Chip({ label, style, className, tone = 'default' }: ChipProps): ReactElement {
  return (
    <span
      style={style}
      className={cn(
        'absolute whitespace-nowrap px-2 py-0.5 rounded-button border text-[9.5px] md:text-[10px] font-medium shadow-xs',
        chipToneClass(tone),
        className
      )}
    >
      {label}
    </span>
  );
}

interface WireProps {
  d: string;
  delay?: string;
  dur?: string;
}

// A connector that visibly draws itself once, using pathLength=1 so the
// dash math works identically regardless of the path's real geometry.
function Wire({ d, delay = '0s', dur = '0.7s' }: WireProps): ReactElement {
  return (
    <path
      d={d}
      pathLength={1}
      stroke="url(#pf-wire)"
      strokeWidth="1.5"
      strokeLinecap="round"
      fill="none"
      className="animate-pf-draw-in"
      style={{ animationDelay: delay, animationDuration: dur }}
    />
  );
}

function SceneDefs(): ReactElement {
  return (
    <defs>
      <linearGradient id="pf-wire" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stopColor="#00baf2" stopOpacity="0.15" />
        <stop offset="100%" stopColor="#005bf5" stopOpacity="0.55" />
      </linearGradient>
    </defs>
  );
}

// ---------------------------------------------------------------------------
// Chapter 1 — the system builds itself. No particle, no title card: a point
// becomes lines, lines become nodes, and PaytmFlow is revealed as part of the
// finished composition (the wordmark itself sits just above this component).
// ---------------------------------------------------------------------------
function BuildScene(): ReactElement {
  const nodes: Array<[number, number]> = [
    [90, 70],
    [310, 70],
    [90, 30],
    [310, 110],
  ];
  return (
    <svg viewBox="0 0 400 150" className="w-full h-full overflow-visible" fill="none">
      <SceneDefs />
      <circle cx="200" cy="70" r="3" className="fill-paytm-blue-action animate-pf-node-in" style={{ animationDelay: '0s' }} />
      <Wire d="M 200 70 L 90 70" delay="0.5s" dur="1.1s" />
      <Wire d="M 200 70 L 310 70" delay="0.5s" dur="1.1s" />
      <Wire d="M 90 70 L 90 30" delay="1.5s" dur="0.7s" />
      <Wire d="M 310 70 L 310 110" delay="1.5s" dur="0.7s" />
      {nodes.map(([cx, cy], i) => (
        <circle
          key={`${cx}-${cy}`}
          cx={cx}
          cy={cy}
          r="4"
          className="fill-paytm-blue-action animate-pf-node-in"
          fillOpacity={0.85}
          style={{ animationDelay: `${1.9 + i * 0.15}s` }}
        />
      ))}
      <circle cx={200} cy={70} r="4" className="fill-paytm-blue-action animate-pf-node-in" fillOpacity={0.85} style={{ animationDelay: '2.5s' }} />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Chapter 2 — a real journey assembles: Goal → Information → Evidence →
// Validation (gate) → Next step, each connecting before the next appears,
// then a live data value travels through the chain.
// ---------------------------------------------------------------------------
const JOURNEY_NODES = [
  { label: 'Goal', x: 40 },
  { label: 'Information', x: 128 },
  { label: 'Evidence', x: 216 },
  { label: 'Validation', x: 304 },
  { label: 'Next step', x: 384 },
];

function AssembleScene(): ReactElement {
  return (
    <div className="relative w-full h-full">
      <svg viewBox="0 0 400 60" className="absolute inset-x-0 top-3 w-full h-10 overflow-visible" fill="none">
        <SceneDefs />
        {JOURNEY_NODES.slice(0, -1).map((n, i) => (
          <Wire key={n.label} d={`M ${n.x} 20 L ${JOURNEY_NODES[i + 1].x} 20`} delay={`${i * 0.9}s`} dur="0.8s" />
        ))}
        {JOURNEY_NODES.map((n, i) => (
          <circle
            key={n.label}
            cx={n.x}
            cy={20}
            r={n.label === 'Validation' ? 6 : 4}
            className="fill-paytm-blue-action animate-pf-node-in"
            fillOpacity={0.85}
            style={{ animationDelay: `${i * 0.9}s` }}
          />
        ))}
      </svg>
      {JOURNEY_NODES.map((n, i) => (
        <Chip
          key={n.label}
          label={n.label}
          tone={n.label === 'Validation' ? 'strong' : 'default'}
          style={{ left: `${(n.x / 400) * 100}%`, top: '48px', animationDelay: `${i * 0.9 + 0.2}s` }}
          className="animate-pf-chip-in"
        />
      ))}
      <span
        className="absolute px-2 py-0.5 rounded-full bg-paytm-cyan/20 border border-paytm-cyan/50 text-[9px] font-semibold text-paytm-blue animate-pf-chip-travel"
        style={
          {
            top: '80px',
            left: `${(JOURNEY_NODES[0].x / 400) * 100}%`,
            '--pf-tx1': `${((JOURNEY_NODES[2].x - JOURNEY_NODES[0].x) / 400) * 100}%`,
            '--pf-tx2': `${((JOURNEY_NODES[3].x - JOURNEY_NODES[0].x) / 400) * 100}%`,
            animationDelay: '4.6s',
          } as CSSProperties
        }
      >
        ₹50,000
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chapter 3 — documents enter from different directions, stack, then
// separate into structured fields that attach onto the journey.
// ---------------------------------------------------------------------------
const DOC_STACK = [
  { label: 'Salary slip', fx: '-90px', fy: '-46px' },
  { label: 'Bank statement', fx: '90px', fy: '-46px' },
  { label: 'Application', fx: '-90px', fy: '38px' },
  { label: 'Identity', fx: '90px', fy: '38px' },
];
const EXTRACTED_FIELDS = [
  { label: 'Income', x: 20 },
  { label: 'Employer', x: 41 },
  { label: 'Account', x: 62 },
  { label: 'Date', x: 79 },
  { label: 'Name', x: 96 },
];

function DocumentsScene(): ReactElement {
  return (
    <div className="relative w-full h-full">
      {DOC_STACK.map((doc, i) => (
        <span
          key={doc.label}
          style={
            {
              '--pf-fx': doc.fx,
              '--pf-fy': doc.fy,
              top: '38%',
              left: '50%',
              animationDelay: `${i * 0.35}s`,
            } as CSSProperties
          }
          className="absolute px-2.5 py-1 rounded-button bg-white border border-surface-border text-[9.5px] font-medium text-content-secondary shadow-xs animate-pf-doc-stack"
        >
          {doc.label}
        </span>
      ))}
      {EXTRACTED_FIELDS.map((field, i) => (
        <Chip
          key={field.label}
          label={field.label}
          tone="strong"
          style={{ left: `${field.x}%`, top: '82%', animationDelay: `${2.4 + i * 0.22}s` }}
          className="animate-pf-field-out"
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chapter 4 — declared information and evidence try to connect; the
// connection hesitates; the flow branches into three candidate paths and
// two of them are visibly de-emphasised.
// ---------------------------------------------------------------------------
function MismatchScene(): ReactElement {
  return (
    <div className="relative w-full h-full">
      <svg viewBox="0 0 400 40" className="absolute inset-x-0 top-1 w-full h-8 overflow-visible" fill="none">
        <path
          d="M 140 20 L 260 20"
          pathLength={1}
          strokeWidth="1.5"
          strokeLinecap="round"
          stroke="#f59e0b"
          strokeDasharray="0.06 0.05"
          className="animate-pf-tension"
        />
      </svg>
      <Chip label="Declared · ₹50,000" style={{ left: '20%', top: '8px' }} className="animate-pf-chip-in" />
      <Chip
        label="Evidence · ₹47,500"
        style={{ left: '80%', top: '8px', animationDelay: '0.3s' }}
        className="animate-pf-chip-in"
      />
      <Chip
        label="Mismatch"
        tone="amber"
        style={{ left: '50%', top: '30px', animationDelay: '1.1s' }}
        className="animate-pf-chip-in"
      />
      <Chip
        label="Correct information"
        tone="muted"
        style={{ left: '18%', top: '64px', animationDelay: '2.1s' }}
        className="animate-pf-branch-in-dim"
      />
      <Chip
        label="Provide evidence"
        tone="strong"
        style={{ left: '50%', top: '64px', animationDelay: '2.1s' }}
        className="animate-pf-branch-in"
      />
      <Chip
        label="Review"
        tone="muted"
        style={{ left: '82%', top: '64px', animationDelay: '2.1s' }}
        className="animate-pf-branch-in-dim"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chapter 5 — AI interpretation and deterministic validation run side by
// side, then converge on one recommendation.
// ---------------------------------------------------------------------------
const AI_STEPS = ['Document', 'Fields', 'Entities', 'Understanding'];
const RULE_CHECKS = ['Evidence present', 'Required information', 'Dependency satisfied', 'Action allowed'];

function IntelligenceScene(): ReactElement {
  return (
    <div className="relative w-full h-full text-[9px] md:text-[9.5px]">
      <span className="absolute left-[6%] top-0 text-[8px] font-semibold uppercase tracking-wide text-content-tertiary animate-pf-label-in">
        AI interpretation
      </span>
      <span
        className="absolute right-[6%] top-0 text-[8px] font-semibold uppercase tracking-wide text-content-tertiary animate-pf-label-in"
        style={{ animationDelay: '0.15s' }}
      >
        Deterministic validation
      </span>
      {AI_STEPS.map((step, i) => (
        <span
          key={step}
          style={{ left: '6%', top: `${16 + i * 17}px`, animationDelay: `${0.4 + i * 0.35}s` }}
          className="absolute px-2 py-0.5 rounded-button bg-white/90 border border-surface-border font-medium text-content-secondary animate-pf-label-in"
        >
          {step}
        </span>
      ))}
      {RULE_CHECKS.map((check, i) => (
        <span
          key={check}
          style={{ right: '6%', top: `${16 + i * 17}px`, animationDelay: `${1.4 + i * 0.3}s` }}
          className="absolute flex items-center gap-1 px-2 py-0.5 rounded-button bg-paytm-green-light border border-paytm-green/30 font-medium text-paytm-green-dark animate-pf-check-in"
        >
          <span aria-hidden="true">✓</span>
          {check}
        </span>
      ))}
      <Chip
        label="Valid next action"
        tone="strong"
        style={{ left: '50%', top: '92px', animationDelay: '3.1s' }}
        className="animate-pf-chip-in"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chapter 6 — four candidate actions are evaluated; invalid ones retract,
// the valid one strengthens, and the journey's state itself flips.
// ---------------------------------------------------------------------------
const CANDIDATES = [
  { label: 'Correct details', valid: false },
  { label: 'Upload evidence', valid: true },
  { label: 'Continue', valid: false },
  { label: 'Request review', valid: false },
];

function ResolveScene(): ReactElement {
  return (
    <div className="relative w-full h-full">
      {/* Desktop/tablet — four candidates evaluated side by side. */}
      <div className="hidden sm:block">
        {CANDIDATES.map((c, i) => (
          <Chip
            key={c.label}
            label={c.label}
            tone={c.valid ? 'strong' : 'muted'}
            style={{ left: `${14 + i * 24}%`, top: '10px', animationDelay: `${i * 0.2}s` }}
            className={c.valid ? 'animate-pf-candidate-in' : 'animate-pf-candidate-in-retract'}
          />
        ))}
        <div className="absolute inset-x-0 top-[52px] flex items-center justify-center h-6" aria-hidden="true">
          <span
            className="absolute left-1/2 px-2.5 py-0.5 rounded-full bg-amber-50 border border-amber-300 text-[9.5px] font-medium text-amber-700 animate-pf-morph-out"
            style={{ animationDelay: '1.6s' }}
          >
            Review required
          </span>
          <span
            className="absolute left-1/2 px-2.5 py-0.5 rounded-full bg-paytm-green-light border border-paytm-green/30 text-[9.5px] font-semibold text-paytm-green-dark animate-pf-morph-in"
            style={{ animationDelay: '2.1s' }}
          >
            Next step
          </span>
        </div>
      </div>

      {/* Mobile — a vertical cascade: each candidate is evaluated in turn,
          invalid ones retract, the valid one strengthens and grows a second
          line connecting it straight to "Next step". Laid out with flexbox
          (not fixed `top:%` slots) so the extra line on the valid card can
          never overlap a neighbouring row — flex reflows around real
          content height instead of assuming every row is the same size. */}
      <div className="sm:hidden absolute inset-0 flex flex-col items-center justify-center gap-1.5 px-4">
        <span className="text-[8px] font-semibold uppercase tracking-wide text-content-tertiary animate-pf-label-in">
          Candidate actions
        </span>
        {CANDIDATES.map((c, i) => (
          <span
            key={c.label}
            style={{ animationDelay: `${0.3 + i * 0.35}s` } as CSSProperties}
            className={cn(
              'flex flex-col items-center gap-0.5 px-3 py-1 rounded-button border text-[9.5px] font-medium shadow-xs w-[86%] max-w-[220px] text-center',
              c.valid
                ? 'bg-paytm-blue-action text-white border-paytm-blue-action shadow-sm animate-pf-cascade-valid'
                : 'bg-white/70 text-content-tertiary border-surface-border animate-pf-cascade-invalid'
            )}
          >
            <span className="whitespace-nowrap">
              {c.label} <span aria-hidden="true">{c.valid ? '✓' : '–'}</span>
            </span>
            {c.valid && (
              <span
                className="text-[8.5px] font-semibold text-white/90 animate-pf-label-in"
                style={{ animationDelay: `${0.3 + i * 0.35 + 0.8}s` }}
              >
                → Next step
              </span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chapter 7 — six journey types, each a small distinct flow shape, connect
// to the same central recovery layer.
// ---------------------------------------------------------------------------
const MINI_JOURNEYS = [
  { label: 'Lending', x: 12, y: 14 },
  { label: 'Insurance', x: 50, y: 4 },
  { label: 'Credit card', x: 88, y: 14 },
  { label: 'KYC', x: 12, y: 78 },
  { label: 'Account opening', x: 50, y: 92 },
  { label: 'Investment', x: 88, y: 78 },
];

function JourneysScene(): ReactElement {
  return (
    <div className="relative w-full h-full">
      <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full overflow-visible" fill="none" preserveAspectRatio="none">
        <SceneDefs />
        {MINI_JOURNEYS.map((j, i) => (
          <Wire key={j.label} d={`M ${j.x} ${j.y} L 50 45`} delay={`${1.2 + i * 0.25}s`} dur="0.6s" />
        ))}
        <circle cx="50" cy="45" r="3" className="fill-paytm-blue-action animate-pf-node-in" style={{ animationDelay: '3.2s' }} />
      </svg>
      {MINI_JOURNEYS.map((j, i) => (
        <Chip
          key={j.label}
          label={j.label}
          style={{ left: `${j.x}%`, top: `${j.y}%`, animationDelay: `${i * 0.25}s` }}
          className="animate-pf-chip-in"
        />
      ))}
      <Chip
        label="Recovery layer"
        tone="strong"
        style={{ left: '50%', top: '45%', animationDelay: '3.4s' }}
        className="animate-pf-chip-in"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chapter 8 — the whole architecture collapses into one FLOW. Four stages,
// so there is never a dead gap: (A) the six journeys converge into the
// Recovery Layer, (B) the layer opens out into its real components, (C) that
// architecture compresses as one group, (D) the FLOW itself emerges strong.
// ---------------------------------------------------------------------------

// Approximate content-box size (the visual sits in a fixed max-w-[22rem]
// column, so this is stable enough to convert %-of-container deltas into the
// px deltas `translate()` actually needs — a % inside translate() resolves
// against the moving element's own box, not the container).
const SCENE_W = 340;
const SCENE_H = 128;
const HUB_X = 50;
const HUB_Y = 45;

function deltaToHub(x: number, y: number): { cx: string; cy: string } {
  return {
    cx: `${((HUB_X - x) / 100) * SCENE_W}px`,
    cy: `${((HUB_Y - y) / 100) * SCENE_H}px`,
  };
}

const ARCH_COMPONENTS = [
  { label: 'Evidence', x: 24, y: 20 },
  { label: 'AI', x: 76, y: 20 },
  { label: 'Rules', x: 76, y: 50 },
  { label: 'Next step', x: 24, y: 50 },
  { label: 'Review', x: 24, y: 80 },
  { label: 'Audit', x: 76, y: 80 },
];
const ARCH_WIRES = [
  [0, 1],
  [1, 2],
  [2, 3],
  [3, 4],
  [4, 5],
] as const;

function ConvergeScene(): ReactElement {
  return (
    <div className="relative w-full h-full">
      {/* Stage A — six journeys converge into the Recovery Layer. */}
      {MINI_JOURNEYS.map((j, i) => {
        const { cx, cy } = deltaToHub(j.x, j.y);
        return (
          <Chip
            key={j.label}
            label={j.label}
            tone="muted"
            style={{ left: `${j.x}%`, top: `${j.y}%`, '--pf-cx': cx, '--pf-cy': cy, animationDelay: `${i * 0.2}s` } as CSSProperties}
            className="animate-pf-collapse-item"
          />
        );
      })}
      <span
        style={{ left: `${HUB_X}%`, top: `${HUB_Y}%` }}
        className="absolute px-2.5 py-1 rounded-button bg-paytm-blue-action text-white border border-paytm-blue-action text-[9.5px] md:text-[10px] font-semibold shadow-sm animate-pf-hub-pulse"
      >
        Recovery layer
      </span>

      {/* Stage B + C — the layer opens into its real components (a
          connected architecture, not six random cards), holds so it reads
          as meaningful, then compresses as one group. */}
      <div className="absolute inset-0 animate-pf-architecture-compress" style={{ animationDelay: '9s' }}>
        <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full overflow-visible" fill="none" preserveAspectRatio="none">
          <SceneDefs />
          {ARCH_WIRES.map(([from, to], i) => (
            <Wire
              key={`${from}-${to}`}
              d={`M ${ARCH_COMPONENTS[from].x} ${ARCH_COMPONENTS[from].y} L ${ARCH_COMPONENTS[to].x} ${ARCH_COMPONENTS[to].y}`}
              delay={`${5.3 + i * 0.3}s`}
              dur="0.6s"
            />
          ))}
        </svg>
        {ARCH_COMPONENTS.map((c, i) => (
          <Chip
            key={c.label}
            label={c.label}
            tone="default"
            style={{ left: `${c.x}%`, top: `${c.y}%`, animationDelay: `${5 + i * 0.25}s` }}
            className="animate-pf-arch-in"
          />
        ))}
      </div>

      {/* Stage D — the FLOW itself emerges, stronger than a decorative spine. */}
      <div className="absolute inset-0 flex items-center justify-center animate-pf-flow-emerge" style={{ animationDelay: '11s' }}>
        <span className="px-3 py-1 rounded-full bg-paytm-blue-action/10 border border-paytm-blue-action/30 text-[9.5px] md:text-[10px] font-semibold text-paytm-blue text-center">
          Explore → Understand → Recover → Complete
        </span>
      </div>
    </div>
  );
}

function SettleScene(): ReactElement {
  return (
    <div className="relative w-full h-full flex items-center justify-center">
      <span
        className="px-3 py-1 rounded-full bg-paytm-blue-action/10 border border-paytm-blue-action/30 text-[10.5px] font-semibold text-paytm-blue animate-pf-label-in"
        style={{ animationDelay: '0.3s' }}
      >
        One flow. Every journey.
      </span>
    </div>
  );
}

function AmbientScene({ label }: { label: string }): ReactElement {
  return (
    <div className="relative w-full h-full flex items-center justify-center">
      <span className="px-2.5 py-1 rounded-button bg-white/80 border border-surface-border text-[10px] font-medium text-content-tertiary shadow-xs animate-pf-ambient-event">
        {label}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Reduced-motion equivalents — the settled composition for each chapter,
// with no animation at all (a single static frame that names the beat).
// ---------------------------------------------------------------------------
const REDUCED_LABELS: Record<ConnectionPhase, string> = {
  build: 'PaytmFlow',
  assemble: 'Goal → Information → Evidence → Validation → Next step',
  documents: 'Documents → structured information',
  mismatch: 'Declared vs. evidence — mismatch found',
  intelligence: 'AI interpretation + rule validation',
  resolve: 'Only the valid action remains',
  journeys: 'Six journeys, one recovery layer',
  converge: 'Everything connects back',
  settle: 'One flow. Every journey.',
  ambient: 'Still here with you.',
};

function ReducedScene({ phase }: { phase: ConnectionPhase }): ReactElement {
  return (
    <div className="flex items-center justify-center h-full">
      <span className="px-2.5 py-1 rounded-button bg-white/90 border border-surface-border text-[10px] font-medium text-content-tertiary shadow-xs">
        {REDUCED_LABELS[phase]}
      </span>
    </div>
  );
}

function renderScene(phase: ConnectionPhase, ambientLabel: string): ReactNode {
  switch (phase) {
    case 'build':
      return <BuildScene />;
    case 'assemble':
      return <AssembleScene />;
    case 'documents':
      return <DocumentsScene />;
    case 'mismatch':
      return <MismatchScene />;
    case 'intelligence':
      return <IntelligenceScene />;
    case 'resolve':
      return <ResolveScene />;
    case 'journeys':
      return <JourneysScene />;
    case 'converge':
      return <ConvergeScene />;
    case 'settle':
      return <SettleScene />;
    case 'ambient':
      return <AmbientScene label={ambientLabel} />;
    default:
      return null;
  }
}

/**
 * The PaytmFlow story, told through actual system transformations — a
 * journey assembling, evidence connecting, invalid paths dropping away, six
 * journeys folding into one recovery layer, everything converging back into
 * the FLOW. Each chapter mounts fresh (keyed by phase) and plays its
 * one-shot choreography once, holding its final frame until the next
 * chapter replaces it. Purely decorative/conceptual — NOT a representation
 * of the viewer's actual journey/document state. Everything here is
 * aria-hidden; the accessible connection status lives alongside it.
 */
export function FlowVisual({ reducedMotion, phase, ambientIndex = 0, ambientLabel = '' }: FlowVisualProps): ReactElement {
  const activeStage = ACTIVE_STAGE[phase];
  const sceneKey = phase === 'ambient' ? `ambient-${ambientIndex}` : phase;

  return (
    <div className="relative w-full max-w-[22rem] md:max-w-md mx-auto" aria-hidden="true">
      {!reducedMotion && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center animate-pf-breathe" aria-hidden="true">
          <div className="w-40 h-40 rounded-full bg-sky-400/20 blur-3xl" />
        </div>
      )}

      <div className="relative h-[128px] md:h-[140px]" key={sceneKey}>
        {reducedMotion ? <ReducedScene phase={phase} /> : renderScene(phase, ambientLabel)}
      </div>

      <svg viewBox="0 0 400 36" className="w-full h-auto overflow-visible mt-1" fill="none">
        <defs>
          <linearGradient id="pf-strip" x1="0" y1="0" x2="400" y2="0" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#00baf2" stopOpacity="0.15" />
            <stop offset="50%" stopColor="#005bf5" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#00baf2" stopOpacity="0.15" />
          </linearGradient>
        </defs>
        <path d={STRIP_PATH_D} stroke="url(#pf-strip)" strokeWidth="2" strokeLinecap="round" />
        {STRIP_STAGE_X.map((x, i) => (
          <circle
            key={STAGES[i]}
            cx={x}
            cy={24 - (i === 1 || i === 2 ? 14 : 0)}
            r={activeStage === i ? 5.5 : 4}
            className={cn('fill-paytm-blue-action', !reducedMotion && activeStage === i && 'animate-pf-node-pulse')}
            fillOpacity={activeStage === i ? 0.9 : 0.4}
          />
        ))}
      </svg>

      <div className="relative mt-1 h-6 text-[10px] md:text-xs font-medium">
        {STAGES.map((stage, i) => (
          <span
            key={stage}
            className={cn(
              'absolute -translate-x-1/2 whitespace-nowrap transition-colors',
              activeStage === i ? 'text-paytm-blue font-semibold' : 'text-content-tertiary'
            )}
            style={{ left: `${(STRIP_STAGE_X[i] / 400) * 100}%` }}
          >
            {stage}
          </span>
        ))}
      </div>
    </div>
  );
}

export default FlowVisual;
