import { forwardRef, useId, type SelectHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';
import { AlertCircle, ChevronDown } from 'lucide-react';

export interface SelectOption {
  value: string | number;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  helperText?: string;
  error?: string;
  options: Array<SelectOption | string>;
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, helperText, error, options, placeholder = 'Select an option', id, className, required, disabled, ...props }, ref) => {
    const generatedId = useId();
    const selectId = id || generatedId;
    const helperId = `${selectId}-helper`;
    const errorId = `${selectId}-error`;
    const hasError = Boolean(error);

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={selectId} className="block text-xs font-semibold text-content-primary mb-1.5">
            {label}
            {required && <span className="text-paytm-red ml-1" aria-hidden="true">*</span>}
          </label>
        )}

        <div className="relative flex items-center">
          <select
            ref={ref}
            id={selectId}
            disabled={disabled}
            aria-invalid={hasError ? 'true' : undefined}
            aria-describedby={hasError ? errorId : helperText ? helperId : undefined}
            className={cn(
              'w-full appearance-none rounded-button bg-surface border border-surface-border pl-3.5 pr-10 py-2 text-sm text-content-primary transition-colors duration-150',
              'focus-visible:ring-2 focus-visible:ring-paytm-cyan focus-visible:border-paytm-cyan focus-visible:outline-none',
              'disabled:bg-surface-muted disabled:text-content-tertiary disabled:cursor-not-allowed',
              hasError && 'border-paytm-red focus-visible:ring-paytm-red focus-visible:border-paytm-red',
              className
            )}
            {...props}
          >
            {placeholder && (
              <option value="" disabled hidden>
                {placeholder}
              </option>
            )}
            {options.map((opt) => {
              if (typeof opt === 'string') {
                return (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                );
              }
              return (
                <option key={String(opt.value)} value={opt.value} disabled={opt.disabled}>
                  {opt.label}
                </option>
              );
            })}
          </select>

          <div className="absolute right-3 inset-y-0 flex items-center pointer-events-none text-content-secondary">
            <ChevronDown className="w-4 h-4 shrink-0" aria-hidden="true" />
          </div>
        </div>

        {hasError ? (
          <p id={errorId} className="mt-1.5 text-xs text-paytm-red flex items-center gap-1">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </p>
        ) : helperText ? (
          <p id={helperId} className="mt-1.5 text-xs text-content-secondary">
            {helperText}
          </p>
        ) : null}
      </div>
    );
  }
);

Select.displayName = 'Select';
export default Select;
