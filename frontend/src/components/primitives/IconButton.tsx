import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { Spinner } from './Spinner';

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: ReactNode;
  'aria-label': string;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  (
    {
      icon,
      className,
      variant = 'ghost',
      size = 'md',
      isLoading = false,
      disabled = false,
      'aria-label': ariaLabel,
      type = 'button',
      ...props
    },
    ref
  ) => {
    const baseStyles =
      'inline-flex items-center justify-center rounded-button transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-paytm-cyan focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed select-none';

    const variantStyles = {
      primary: 'bg-paytm-blue text-white hover:bg-paytm-blue-700 active:bg-paytm-blue-dark shadow-sm',
      secondary: 'bg-surface-subtle text-content-primary hover:bg-surface-border border border-surface-border',
      ghost: 'bg-transparent text-content-secondary hover:bg-surface-subtle hover:text-content-primary',
      danger: 'bg-paytm-red text-white hover:bg-paytm-red-dark',
    };

    const sizeStyles = {
      sm: 'w-8 h-8 p-1.5',
      md: 'w-10 h-10 p-2',
      lg: 'w-12 h-12 p-3',
    };

    return (
      <button
        ref={ref}
        type={type}
        aria-label={ariaLabel}
        disabled={disabled || isLoading}
        className={cn(baseStyles, variantStyles[variant], sizeStyles[size], className)}
        {...props}
      >
        {isLoading ? <Spinner size="sm" className="text-current" /> : icon}
      </button>
    );
  }
);

IconButton.displayName = 'IconButton';
export default IconButton;
