import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  hoverEffect?: boolean;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  variant?: 'default' | 'subtle' | 'tinted-blue' | 'tinted-amber' | 'tinted-green' | 'tinted-red';
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ children, className, hoverEffect = false, padding = 'md', variant = 'default', ...props }, ref) => {
    const paddingStyles = {
      none: 'p-0',
      sm: 'p-4',
      md: 'p-6',
      lg: 'p-8',
    };

    const variantStyles = {
      default: 'bg-surface border border-surface-border text-content-primary',
      subtle: 'bg-surface-muted border border-surface-border text-content-primary',
      'tinted-blue': 'bg-paytm-blue-50 border border-paytm-blue-100 text-paytm-blue-700',
      'tinted-amber': 'bg-paytm-amber-light border border-amber-200 text-paytm-amber-dark',
      'tinted-green': 'bg-paytm-green-light border border-green-200 text-paytm-green-dark',
      'tinted-red': 'bg-paytm-red-light border border-red-200 text-paytm-red-dark',
    };

    return (
      <div
        ref={ref}
        className={cn(
          'rounded-card shadow-card transition-all duration-150',
          variantStyles[variant],
          paddingStyles[padding],
          hoverEffect && 'hover:shadow-card-hover hover:border-slate-300 cursor-pointer',
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';
export default Card;
