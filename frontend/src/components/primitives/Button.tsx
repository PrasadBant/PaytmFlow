import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { Spinner } from './Spinner';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'cyan' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      children,
      className,
      variant = 'primary',
      size = 'md',
      isLoading = false,
      disabled = false,
      leftIcon,
      rightIcon,
      type = 'button',
      ...props
    },
    ref
  ) => {
    const baseStyles =
      'inline-flex items-center justify-center font-medium rounded-button transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-paytm-cyan focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed select-none';

    const variantStyles = {
      primary: 'bg-paytm-blue-action text-white hover:bg-paytm-blue-action-hover active:bg-[#003db3] shadow-sm font-semibold',
      secondary: 'bg-white text-content-primary hover:bg-surface-subtle active:bg-slate-200 border border-surface-border font-medium',
      ghost: 'bg-transparent text-content-secondary hover:bg-surface-subtle hover:text-content-primary active:bg-surface-border',
      danger: 'bg-paytm-red text-white hover:bg-paytm-red-dark active:bg-red-800 shadow-sm',
      cyan: 'bg-paytm-cyan text-white hover:bg-[#00a2d4] active:bg-[#008cb7] shadow-sm',
      outline: 'bg-white text-paytm-blue-action border border-paytm-blue-action hover:bg-paytm-blue-50 active:bg-paytm-blue-100 font-semibold',
    };

    const sizeStyles = {
      sm: 'text-xs px-3 py-1.5 gap-1.5 h-8',
      md: 'text-sm px-4 py-2 gap-2 h-10',
      lg: 'text-base px-6 py-3 gap-2.5 h-12',
    };

    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled || isLoading}
        className={cn(baseStyles, variantStyles[variant], sizeStyles[size], className)}
        {...props}
      >
        {isLoading ? (
          <>
            <Spinner size={size === 'lg' ? 'md' : 'sm'} className="text-current" />
            <span>{children}</span>
          </>
        ) : (
          <>
            {leftIcon && <span className="inline-flex shrink-0 items-center">{leftIcon}</span>}
            <span className="inline-flex items-center gap-1.5">{children}</span>
            {rightIcon && <span className="inline-flex shrink-0 items-center">{rightIcon}</span>}
          </>
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';
export default Button;
