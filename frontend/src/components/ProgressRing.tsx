import type { ReactElement } from 'react';
import { cn } from '@/lib/utils';

export interface ProgressRingProps {
  completed: number;
  total: number;
  size?: 'sm' | 'md' | 'lg' | number;
  strokeWidth?: number;
  className?: string;
  sublabel?: string;
  ariaLabel?: string;
}

export function ProgressRing({
  completed,
  total,
  size = 'md',
  strokeWidth,
  className,
  sublabel = 'Completed',
  ariaLabel,
}: ProgressRingProps): ReactElement {
  const sizePx =
    typeof size === 'number'
      ? size
      : size === 'sm'
        ? 88
        : size === 'lg'
          ? 160
          : 128;

  const stroke = strokeWidth ?? (sizePx <= 88 ? 7 : sizePx <= 128 ? 9 : 12);
  const radius = (sizePx - stroke) / 2;
  const circumference = 2 * Math.PI * radius;

  const safeTotal = Math.max(0, total);
  const safeCompleted = Math.max(0, Math.min(completed, safeTotal || 1));
  const progressRatio = safeTotal > 0 ? safeCompleted / safeTotal : 0;
  const strokeDashoffset = circumference - progressRatio * circumference;

  const countClass =
    sizePx <= 88 ? 'text-lg' : sizePx <= 128 ? 'text-2xl' : 'text-3xl';
  const labelClass =
    sizePx <= 88 ? 'text-[10px]' : sizePx <= 128 ? 'text-xs' : 'text-sm';

  const accessibleLabel =
    ariaLabel ?? `${safeCompleted} of ${safeTotal} steps completed`;

  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={safeTotal}
      aria-valuenow={safeCompleted}
      aria-label={accessibleLabel}
      className={cn('relative inline-flex items-center justify-center shrink-0', className)}
      style={{ width: sizePx, height: sizePx }}
      data-testid="progress-ring"
    >
      <svg
        width={sizePx}
        height={sizePx}
        viewBox={`0 0 ${sizePx} ${sizePx}`}
        className="transform -rotate-90"
        aria-hidden="true"
      >
        {/* Background track circle */}
        <circle
          cx={sizePx / 2}
          cy={sizePx / 2}
          r={radius}
          stroke="var(--pf-color-surface-border)"
          strokeWidth={stroke}
          fill="transparent"
          className="transition-colors"
        />

        {/* Foreground progress circle */}
        <circle
          cx={sizePx / 2}
          cy={sizePx / 2}
          r={radius}
          stroke="var(--pf-color-paytm-green)"
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          fill="transparent"
          className="transition-all duration-500 ease-out"
        />
      </svg>

      {/* Centre text content: {completed}/{total} and "Completed" */}
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none select-none">
        <span
          data-testid="progress-ring-count"
          className={cn('font-bold text-content-primary tracking-tight leading-none', countClass)}
        >
          {safeCompleted}/{safeTotal}
        </span>
        <span
          data-testid="progress-ring-label"
          className={cn('font-medium text-content-secondary mt-1 tracking-wide', labelClass)}
        >
          {sublabel}
        </span>
      </div>
    </div>
  );
}

export default ProgressRing;
