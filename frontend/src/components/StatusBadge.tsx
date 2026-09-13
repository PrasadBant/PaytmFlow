import type { HTMLAttributes, ReactElement, ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { CheckCircle2, AlertCircle, AlertTriangle, Clock } from 'lucide-react';
import type { components } from '@/api/types.gen';

export type FieldStatus = components['schemas']['FieldStatus'];
export type Readiness = components['schemas']['Readiness'];
export type JourneyStatus = components['schemas']['JourneyStatus'];

export type AnyStatus =
  | FieldStatus
  | Readiness
  | JourneyStatus
  | 'PENDING'
  | 'NOT_STARTED'
  | 'IN_PROGRESS';

export interface StatusBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  status: AnyStatus | string;
  label?: string;
  icon?: ReactNode;
  size?: 'sm' | 'md';
}

interface StatusConfig {
  variantStyle: string;
  defaultLabel: string;
  icon: ReactElement;
}

export function StatusBadge({
  status,
  label,
  icon,
  size = 'md',
  className,
  ...props
}: StatusBadgeProps): ReactElement {
  const normalized = String(status).toUpperCase();

  const configs: Record<string, StatusConfig> = {
    SATISFIED: {
      variantStyle: 'bg-paytm-green-light text-paytm-green-dark border-green-200',
      defaultLabel: 'Satisfied',
      icon: <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-paytm-green" aria-hidden="true" />,
    },
    COMPLETED: {
      variantStyle: 'bg-paytm-green-light text-paytm-green-dark border-green-200',
      defaultLabel: 'Completed',
      icon: <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-paytm-green" aria-hidden="true" />,
    },
    READY: {
      variantStyle: 'bg-paytm-green-light text-paytm-green-dark border-green-200',
      defaultLabel: 'Ready',
      icon: <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-paytm-green" aria-hidden="true" />,
    },
    BLOCKED: {
      variantStyle: 'bg-paytm-red-light text-paytm-red-dark border-red-200',
      defaultLabel: 'Blocked',
      icon: <AlertCircle className="w-3.5 h-3.5 shrink-0 text-paytm-red" aria-hidden="true" />,
    },
    DEAD_END: {
      variantStyle: 'bg-paytm-red-light text-paytm-red-dark border-red-200',
      defaultLabel: 'Dead End',
      icon: <AlertCircle className="w-3.5 h-3.5 shrink-0 text-paytm-red" aria-hidden="true" />,
    },
    AMBIGUOUS: {
      variantStyle: 'bg-paytm-amber-light text-paytm-amber-dark border-amber-200',
      defaultLabel: 'Needs Review',
      icon: <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-paytm-amber" aria-hidden="true" />,
    },
    NEEDS_REVIEW: {
      variantStyle: 'bg-paytm-amber-light text-paytm-amber-dark border-amber-200',
      defaultLabel: 'Needs Review',
      icon: <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-paytm-amber" aria-hidden="true" />,
    },
    PENDING: {
      variantStyle: 'bg-surface-subtle text-content-secondary border-surface-border',
      defaultLabel: 'Pending',
      icon: <Clock className="w-3.5 h-3.5 shrink-0 text-content-tertiary" aria-hidden="true" />,
    },
    IN_PROGRESS: {
      variantStyle: 'bg-paytm-blue-50 text-paytm-blue-600 border-paytm-blue-100',
      defaultLabel: 'In Progress',
      icon: <Clock className="w-3.5 h-3.5 shrink-0 text-paytm-blue" aria-hidden="true" />,
    },
    NOT_READY: {
      variantStyle: 'bg-paytm-blue-50 text-paytm-blue-600 border-paytm-blue-100',
      defaultLabel: 'In Progress',
      icon: <Clock className="w-3.5 h-3.5 shrink-0 text-paytm-blue" aria-hidden="true" />,
    },
  };

  const config = configs[normalized] || {
    variantStyle: 'bg-surface-subtle text-content-secondary border-surface-border',
    defaultLabel: normalized,
    icon: <Clock className="w-3.5 h-3.5 shrink-0 text-content-tertiary" aria-hidden="true" />,
  };

  const displayLabel = label ?? config.defaultLabel;
  const displayIcon = icon !== undefined ? icon : config.icon;
  const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-badge font-semibold border select-none transition-colors',
        sizeClass,
        config.variantStyle,
        className
      )}
      data-testid="status-badge"
      {...props}
    >
      {displayIcon}
      <span>{displayLabel}</span>
    </span>
  );
}

export default StatusBadge;
