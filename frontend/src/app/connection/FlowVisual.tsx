import type { CSSProperties, ReactElement } from 'react';
import { cn } from '@/lib/utils';

export interface FlowVisualProps {
  /** SMIL particle motion can't be paused via CSS — gate it explicitly. */
  reducedMotion: boolean;
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

const AMBIENT_DOTS: Array<{ style: CSSProperties; delay: string }> = [
  { style: { top: '8%', left: '18%' }, delay: '0s' },
  { style: { top: '68%', left: '8%' }, delay: '2.5s' },
  { style: { top: '20%', right: '12%' }, delay: '5s' },
  { style: { top: '78%', right: '20%' }, delay: '7.5s' },
];

// Roughly matches when the primary particle (dur=4.5s) passes each node,
// so a node's arrival glow feels connected to the flow rather than random.
const NODE_ARRIVAL_DELAYS = ['0s', '1.5s', '3s', '4.5s'];

/**
 * Purely decorative "flow" metaphor for PaytmFlow's product concept — NOT a
 * representation of the viewer's actual journey/document state. Everything
 * here is aria-hidden; the accessible connection status lives alongside it.
 */
export function FlowVisual({ reducedMotion }: FlowVisualProps): ReactElement {
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
        <div className="pointer-events-none absolute inset-0 hidden md:block">
          {AMBIENT_DOTS.map((dot, i) => (
            <span
              key={i}
              style={{ ...dot.style, animationDelay: dot.delay }}
              className="absolute w-1.5 h-1.5 rounded-full bg-paytm-cyan blur-[1px] animate-pf-ambient"
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
            <feGaussianBlur stdDeviation="2.2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Layer 1 — base path */}
        <path d={FLOW_PATH_D} stroke="url(#pf-flow-base)" strokeWidth="2.5" strokeLinecap="round" />

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
              style={!reducedMotion ? { animationDelay: NODE_ARRIVAL_DELAYS[i] } : undefined}
            />
            <circle cx={cx} cy={cy} r="4" className="fill-paytm-blue-action" fillOpacity={0.85} />
          </g>
        ))}

        {/* Layer 3 — primary particle + a very subtle trail */}
        {!reducedMotion && (
          <>
            <circle r="2" className="fill-paytm-cyan" fillOpacity={0.35}>
              <animateMotion dur="4.5s" begin="-0.3s" repeatCount="indefinite" keyPoints="0;1" keyTimes="0;1" calcMode="spline" keySplines="0.42 0 0.58 1">
                <mpath href="#pf-flow-path" />
              </animateMotion>
            </circle>
            <circle r="2.6" className="fill-paytm-cyan" fillOpacity={0.55}>
              <animateMotion dur="4.5s" begin="-0.15s" repeatCount="indefinite" keyPoints="0;1" keyTimes="0;1" calcMode="spline" keySplines="0.42 0 0.58 1">
                <mpath href="#pf-flow-path" />
              </animateMotion>
            </circle>
            <circle r="4.5" className="fill-paytm-cyan" filter="url(#pf-flow-glow)">
              <animateMotion dur="4.5s" repeatCount="indefinite" keyPoints="0;1" keyTimes="0;1" calcMode="spline" keySplines="0.42 0 0.58 1">
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

      {!reducedMotion && (
        <div className="pointer-events-none absolute inset-0 hidden sm:block">
          {CONCEPT_CARDS.map((card) => (
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
                'absolute px-2.5 py-1 rounded-button bg-white/85 border border-surface-border text-[10px] font-medium text-content-tertiary shadow-xs backdrop-blur-sm animate-pf-card-flow',
                card.className
              )}
            >
              {card.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default FlowVisual;
