import type { HTMLAttributes, ReactElement, ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { CheckCircle2, AlertCircle, AlertTriangle, Sparkles, Clock, HelpCircle } from 'lucide-react';

export type BadgeVariant =
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'neutral'
  | 'flagship'
  | 'amber';

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  icon?: ReactNode;
  showDefaultIcon?: boolean;
}

export function Badge({
  children,
  className,
  variant = 'neutral',
  icon,
  showDefaultIcon = true,
  ...props
}: BadgeProps): ReactElement {
  const variantStyles: Record<BadgeVariant, string> = {
    success: 'bg-paytm-green-light text-paytm-green-dark border-green-200',
    warning: 'bg-paytm-amber-light text-paytm-amber-dark border-amber-200',
    amber: 'bg-paytm-amber-light text-paytm-amber-dark border-amber-200',
    danger: 'bg-paytm-red-light text-paytm-red-dark border-red-200',
    info: 'bg-paytm-cyan-light text-paytm-blue border-cyan-200',
    neutral: 'bg-surface-subtle text-content-secondary border-surface-border',
    flagship: 'bg-paytm-blue-action text-white border-transparent shadow-xs',
  };

  const defaultIcons: Record<BadgeVariant, ReactNode> = {
    success: <CheckCircle2 className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />,
    warning: <AlertTriangle className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />,
    amber: <AlertTriangle className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />,
    danger: <AlertCircle className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />,
    info: <Clock className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />,
    neutral: <HelpCircle className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />,
    flagship: <Sparkles className="w-3.5 h-3.5 text-paytm-cyan shrink-0" aria-hidden="true" />,
  };

  const activeIcon = icon !== undefined ? icon : showDefaultIcon ? defaultIcons[variant] : null;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-badge text-xs font-semibold border select-none',
        variantStyles[variant],
        className
      )}
      {...props}
    >
      {activeIcon}
      <span>{children}</span>
    </span>
  );
}

export default Badge;
