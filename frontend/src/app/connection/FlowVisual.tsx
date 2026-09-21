import type { CSSProperties, ReactElement } from 'react';
import { cn } from '@/lib/utils';
import type { ConnectionPhase } from './connectionPhases';

export interface FlowVisualProps {
  /** SMIL particle motion can't be paused via CSS — gate it explicitly. */
  reducedMotion: boolean;
  /** Which broad story beat is currently showing — governs choreography only. */
  phase: ConnectionPhase;
}

const STAGES = ['Explore', 'Understand', 'Recover', 'Complete'];

// Exact points on the single cubic Bézier below (t = 0, 1/3, 2/3, 1) so each
// node sits precisely on the curve rather than an eyeballed approximation.
const STAGE_POINTS: Array<[number, number]> = [
  [24, 96],
  [138.8, 43.4],
  [261.2, 29.9],
  [376, 44],
];

// One continuous, single-hump curve — deliberately not a zigzag or a
// multi-hump wave. Reads as one flowing stream rather than a progress bar.
const FLOW_PATH_D = 'M 24 96 C 130 20, 270 20, 376 44';

// The "recovery" story beat — a second, alternate path that appears once
// alongside the "Recover" node before dissolving. Purely conceptual
// (nothing here reflects the viewer's real document state).
const ALT_PATH_D = 'M 200 62 C 225 92, 255 88, 280 58';

// Anchored to only the two corners proven clear of both the curve and the
// stage labels (top-left / top-right) — the container is too compact for
// four distinct safe positions. Cards are time-multiplexed (each visible
// for well under a third of the shared cycle), so pairing two concepts per
// corner never shows a meaningful double-exposure, only a brief soft tail.
const CONCEPT_CARDS: Array<{ label: string; className: string; delay: string; dx: string; dy: string }> = [
  { label: 'Documents', className: 'top-0 left-0 md:left-6', delay: '0s', dx: '36px', dy: '18px' },
  { label: 'Verification', className: 'top-0 right-0 md:right-6', delay: '1.6s', dx: '-32px', dy: '18px' },
  { label: 'Application', className: 'top-0 left-0 md:left-6', delay: '3.2s', dx: '36px', dy: '18px' },
  { label: 'Next step', className: 'top-0 right-0 md:right-6', delay: '4.8s', dx: '-32px', dy: '18px' },
];

// The "journey ecosystem" beat — each of the six journeys PaytmFlow covers
// briefly connects to the central flow before the story reassembles.
const JOURNEY_CARDS: Array<{ label: string; className: string; delay: string; dx: string; dy: string }> = [
  { label: 'Lending', className: 'top-0 left-0 md:left-6', delay: '0s', dx: '36px', dy: '18px' },
  { label: 'Insurance', className: 'top-0 right-0 md:right-6', delay: '1.6s', dx: '-32px', dy: '18px' },
  { label: 'Credit card', className: 'top-0 left-0 md:left-6', delay: '3.2s', dx: '36px', dy: '18px' },
  { label: 'KYC', className: 'top-0 right-0 md:right-6', delay: '4.8s', dx: '-32px', dy: '18px' },
  { label: 'Account opening', className: 'top-0 left-0 md:left-6', delay: '6.4s', dx: '36px', dy: '18px' },
  { label: 'Investment', className: 'top-0 right-0 md:right-6', delay: '8s', dx: '-32px', dy: '18px' },
];

// The "reassembly" beat — a couple of earlier concepts return once, this
// time converging INTO the flow (opposite direction/feel from the drifting
// concept/journey cards) before the flow settles into ambient mode.
const REASSEMBLY_CARDS: Array<{ label: string; className: string; delay: string; dx: string; dy: string }> = [
  { label: 'Documents', className: 'top-0 left-0 md:left-6', delay: '0s', dx: '160px', dy: '30px' },
  { label: 'Next step', className: 'top-0 right-0 md:right-6', delay: '4.5s', dx: '-150px', dy: '30px' },
];

// Six journeys, shown one at a time in a single compact slot — the mobile
// substitute for the desktop journey cards (no corner layout, no travel, so
// nothing can overflow a narrow viewport).
const MOBILE_JOURNEY_LABELS = ['Lending', 'Insurance', 'Credit card', 'KYC', 'Account opening', 'Investment'];
const MOBILE_JOURNEY_DELAY_STEP = 3.2;
const MOBILE_JOURNEY_CYCLE = MOBILE_JOURNEY_LABELS.length * MOBILE_JOURNEY_DELAY_STEP;

const MOBILE_REASSEMBLY_LABELS = ['Documents', 'Next step'];
const MOBILE_REASSEMBLY_DELAY_STEP = 4.5;

const AMBIENT_DOTS: Array<{ style: CSSProperties; delay: string }> = [
  { style: { top: '8%', left: '18%' }, delay: '0s' },
  { style: { top: '68%', left: '8%' }, delay: '1.2s' },
  { style: { top: '20%', right: '12%' }, delay: '2.4s' },
  { style: { top: '78%', right: '20%' }, delay: '3.6s' },
  { style: { top: '42%', left: '4%' }, delay: '0.8s' },
  { style: { top: '55%', right: '6%' }, delay: '2.9s' },
  { style: { top: '4%', left: '48%' }, delay: '1.8s' },
];

// Roughly matches when the primary particle (dur=4.5s) passes each node,
// so a node's arrival glow feels connected to the flow rather than random.
const NODE_ARRIVAL_DELAYS = ['0s', '1.5s', '3s', '4.5s'];

// Sequential one-shot illumination during reassembly — deliberately spaced
// well after the two reassembly cards have converged (each card's own
// converge animation runs ~4s), so this reads as its own beat rather than
// overlapping the card motion.
const REASSEMBLE_NODE_DELAYS = ['9s', '9.35s', '9.7s', '10.05s'];

const PARTICLE_DUR_MS: Record<ConnectionPhase, string> = {
  intro: '4.5s',
  discovery: '4.5s',
  recovery: '4.5s',
  journeys: '4.5s',
  reassembly: '5s',
  ambient: '6.5s',
};

/**
 * Purely decorative "flow" metaphor for PaytmFlow's product concept — NOT a
 * representation of the viewer's actual journey/document state. Everything
 * here is aria-hidden; the accessible connection status lives alongside it.
 */
export function FlowVisual({ reducedMotion, phase }: FlowVisualProps): ReactElement {
  const showConceptCards = !reducedMotion && phase === 'discovery';
  const showJourneyCards = !reducedMotion && phase === 'journeys';
  const showReassemblyCards = !reducedMotion && phase === 'reassembly';
  const showRecovery = !reducedMotion && phase === 'recovery';
  const isAmbient = phase === 'ambient';
  const particleDur = PARTICLE_DUR_MS[phase];

  return (
    <div className="relative w-full max-w-[22rem] md:max-w-md mx-auto" aria-hidden="true">
      {/*
        Deliberately NOT negative z-index: an in-flow, non-positioned SVG
        sibling paints above a negative-z-index layer in this rendering
        pipeline even where the SVG is visually transparent, which made this
        entire layer invisible. Default (auto) stacking + DOM order after the
        svg keeps it visible while still reading as a background layer.
      */}
      {!reducedMotion && (
        <div
          className={cn(
            'pointer-events-none absolute inset-0 flex items-center justify-center animate-pf-breathe',
            isAmbient && 'opacity-70'
          )}
          aria-hidden="true"
        >
          <div className="w-40 h-40 rounded-full bg-sky-400/20 blur-3xl" />
        </div>
      )}

      {/*
        Ambient dots stay deliberately smaller/dimmer than the primary flow
        particle (see the glow filter + brighter core below) — they're
        atmosphere, never a competitor for "which dot is the one that matters".
      */}
      {!reducedMotion && (
        <div className="pointer-events-none absolute inset-0 hidden md:block">
          {(isAmbient ? AMBIENT_DOTS.slice(0, 3) : AMBIENT_DOTS).map((dot, i) => (
            <span
              key={i}
              style={{ ...dot.style, animationDelay: dot.delay }}
              className="absolute w-1 h-1 rounded-full bg-paytm-cyan blur-[1px] animate-pf-ambient"
            />
          ))}
        </div>
      )}

      <svg viewBox="0 0 400 130" className="w-full h-auto overflow-visible" fill="none">
        <defs>
          <linearGradient id="pf-flow-base" x1="0" y1="0" x2="400" y2="0" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#00baf2" stopOpacity="0.1" />
            <stop offset="50%" stopColor="#005bf5" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#00baf2" stopOpacity="0.1" />
          </linearGradient>
          <linearGradient id="pf-flow-highlight" x1="0" y1="0" x2="400" y2="0" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#00baf2" stopOpacity="0" />
            <stop offset="50%" stopColor="#00baf2" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#005bf5" stopOpacity="0" />
          </linearGradient>
          <filter id="pf-flow-glow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Layer 1 — base path */}
        <path d={FLOW_PATH_D} stroke="url(#pf-flow-base)" strokeWidth="2.5" strokeLinecap="round" />

        {/*
          Recovery beat — ONE cinematic event, not a loop. The dashed guide
          path and its particle live in the same <g>, sharing one opacity
          animation, so the particle can never be visible while the path
          isn't (the exact "path invisible, particle still floating" glitch
          this replaces). Mounted only while phase === 'recovery' and plays
          its single 7s reveal -> hold -> dissolve cycle exactly once.
        */}
        {showRecovery && (
          <g className="animate-pf-recovery-path">
            <path
              id="pf-flow-alt-path"
              d={ALT_PATH_D}
              stroke="url(#pf-flow-base)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeDasharray="4 5"
            />
            <circle r="2.2" className="fill-paytm-blue-action">
              <animateMotion dur="2.6s" begin="1.2s" repeatCount="1" fill="freeze" keyPoints="0;1" keyTimes="0;1" calcMode="spline" keySplines="0.42 0 0.58 1">
                <mpath href="#pf-flow-alt-path" />
              </animateMotion>
            </circle>
          </g>
        )}
        {reducedMotion && phase === 'recovery' && (
          <path
            d={ALT_PATH_D}
            stroke="url(#pf-flow-base)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray="4 5"
            opacity={0.55}
          />
        )}

        {/* Reassembly beat — the flow itself briefly reads brighter once, as the story concludes */}
        {showReassemblyCards && (
          <path
            d={FLOW_PATH_D}
            stroke="url(#pf-flow-highlight)"
            strokeWidth="3.5"
            strokeLinecap="round"
            opacity={0}
            className="animate-pf-reassemble-glow"
          />
        )}

        {/* Layer 2 — soft moving highlight along the same path */}
        {!reducedMotion && (
          <path
            id="pf-flow-path"
            d={FLOW_PATH_D}
            stroke="url(#pf-flow-highlight)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeDasharray="60 500"
            className="animate-pf-highlight"
          />
        )}
        {reducedMotion && <path id="pf-flow-path" d={FLOW_PATH_D} stroke="none" />}

        {/* Layer 4 — stage nodes: halo + core, with an arrival pulse timed to the particle */}
        {STAGE_POINTS.map(([cx, cy], i) => (
          <g key={STAGES[i]}>
            <circle
              cx={cx}
              cy={cy}
              r="9"
              className={cn('fill-paytm-blue-action', !reducedMotion && 'animate-pf-node-pulse')}
              fillOpacity={0.14}
              style={
                !reducedMotion
                  ? { animationDelay: NODE_ARRIVAL_DELAYS[i], animationDuration: particleDur }
                  : undefined
              }
            />
            {showReassemblyCards && (
              <circle
                cx={cx}
                cy={cy}
                r="9"
                className="fill-paytm-blue-action animate-pf-reassemble-node"
                fillOpacity={0.14}
                style={{ animationDelay: REASSEMBLE_NODE_DELAYS[i] }}
              />
            )}
            {showRecovery && i === 2 && (
              <circle
                cx={cx}
                cy={cy}
                r="9"
                className="fill-paytm-cyan animate-pf-recovery-ring"
                fillOpacity={0}
              />
            )}
            <circle cx={cx} cy={cy} r="4" className="fill-paytm-blue-action" fillOpacity={0.85} />
          </g>
        ))}

        {/*
          Layer 3 — primary particle. Kept unmistakably the brightest, most
          contrasted moving element on screen: a soft trail (dim, small),
          then a glowing core, then a brighter near-white highlight riding
          on top of that core — nothing else on this screen combines size +
          brightness + glow the way this does.
        */}
        {!reducedMotion && (
          <>
            <circle r="2" className="fill-paytm-cyan" fillOpacity={0.4}>
              <animateMotion dur={particleDur} begin="-0.3s" repeatCount="indefinite" keyPoints="0;1" keyTimes="0;1" calcMode="spline" keySplines="0.42 0 0.58 1">
                <mpath href="#pf-flow-path" />
              </animateMotion>
            </circle>
            <circle r="2.8" className="fill-paytm-cyan" fillOpacity={0.65}>
              <animateMotion dur={particleDur} begin="-0.15s" repeatCount="indefinite" keyPoints="0;1" keyTimes="0;1" calcMode="spline" keySplines="0.42 0 0.58 1">
                <mpath href="#pf-flow-path" />
              </animateMotion>
            </circle>
            <circle r="5.5" className="fill-paytm-cyan" filter="url(#pf-flow-glow)">
              <animateMotion dur={particleDur} repeatCount="indefinite" keyPoints="0;1" keyTimes="0;1" calcMode="spline" keySplines="0.42 0 0.58 1">
                <mpath href="#pf-flow-path" />
              </animateMotion>
            </circle>
            <circle r="2" fill="#eafcff">
              <animateMotion dur={particleDur} repeatCount="indefinite" keyPoints="0;1" keyTimes="0;1" calcMode="spline" keySplines="0.42 0 0.58 1">
                <mpath href="#pf-flow-path" />
              </animateMotion>
            </circle>
          </>
        )}
        {reducedMotion && <circle cx={STAGE_POINTS[0][0]} cy={STAGE_POINTS[0][1]} r="4.5" className="fill-paytm-cyan" />}
      </svg>

      <div className="relative mt-1 h-8 text-[10px] md:text-xs font-medium text-content-tertiary">
        {STAGES.map((stage, i) => (
          <span
            key={stage}
            className="absolute -translate-x-1/2 whitespace-nowrap"
            style={{ left: `${(STAGE_POINTS[i][0] / 400) * 100}%` }}
          >
            {stage}
          </span>
        ))}
      </div>

      {/* Desktop/tablet choreography: cards drift in from, or converge back toward, the flow's corners */}
      {(showConceptCards || showJourneyCards || showReassemblyCards) && (
        <div className="pointer-events-none absolute inset-0 hidden sm:block">
          {(showConceptCards ? CONCEPT_CARDS : showJourneyCards ? JOURNEY_CARDS : REASSEMBLY_CARDS).map((card) => (
            <span
              key={card.label}
              style={
                {
                  animationDelay: card.delay,
                  '--pf-card-dx': card.dx,
                  '--pf-card-dy': card.dy,
                } as CSSProperties
              }
              className={cn(
                'absolute px-2.5 py-1 rounded-button bg-white/85 border border-surface-border text-[10px] font-medium text-content-tertiary shadow-xs backdrop-blur-sm',
                showReassemblyCards ? 'animate-pf-reassemble-converge' : 'animate-pf-card-flow',
                card.className
              )}
            >
              {card.label}
            </span>
          ))}
        </div>
      )}

      {/*
        Mobile-only choreography — a single compact slot, not the desktop
        cards at a smaller size. One label at a time, fading in place with a
        soft cyan glow to suggest "this briefly connects to the flow", then
        fading out before the next appears. Nothing here can overflow a
        390px viewport since nothing travels sideways.
      */}
      {!reducedMotion && phase === 'journeys' && (
        <div className="pointer-events-none absolute inset-x-0 -top-1 flex justify-center sm:hidden">
          {MOBILE_JOURNEY_LABELS.map((label, i) => (
            <span
              key={label}
              style={{
                animationDelay: `${i * MOBILE_JOURNEY_DELAY_STEP}s`,
                animationDuration: `${MOBILE_JOURNEY_CYCLE}s`,
              }}
              className="absolute px-2.5 py-1 rounded-button bg-white/90 border border-surface-border text-[10px] font-medium text-content-tertiary shadow-xs shadow-paytm-cyan/30 animate-pf-mobile-pill"
            >
              {label}
            </span>
          ))}
        </div>
      )}
      {!reducedMotion && phase === 'reassembly' && (
        <div className="pointer-events-none absolute inset-x-0 -top-1 flex justify-center sm:hidden">
          {MOBILE_REASSEMBLY_LABELS.map((label, i) => (
            <span
              key={label}
              style={{ animationDelay: `${i * MOBILE_REASSEMBLY_DELAY_STEP}s` }}
              className="absolute px-2.5 py-1 rounded-button bg-white/90 border border-surface-border text-[10px] font-medium text-content-tertiary shadow-xs shadow-paytm-cyan/30 animate-pf-mobile-converge"
            >
              {label}
            </span>
          ))}
        </div>
      )}
      {reducedMotion && (phase === 'discovery' || phase === 'journeys' || phase === 'reassembly') && (
        <div className="flex justify-center mt-1">
          <span className="px-2.5 py-1 rounded-button bg-white/90 border border-surface-border text-[10px] font-medium text-content-tertiary shadow-xs">
            {phase === 'discovery' ? 'Documents' : phase === 'journeys' ? 'Six journeys, one flow' : 'Bringing it together'}
          </span>
        </div>
      )}
    </div>
  );
}

export default FlowVisual;
