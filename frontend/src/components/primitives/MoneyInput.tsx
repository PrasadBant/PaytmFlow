import { forwardRef, useState, useEffect, useId, type ChangeEvent, type FocusEvent } from 'react';
import { cn, formatIndianCurrency, parseIndianCurrency } from '@/lib/utils';
import { AlertCircle } from 'lucide-react';

export interface MoneyInputProps {
  label?: string;
  helperText?: string;
  error?: string;
  value?: number | string;
  defaultValue?: number | string;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  id?: string;
  name?: string;
  className?: string;
  onChange?: (value: number | null) => void;
  onBlur?: (e: FocusEvent<HTMLInputElement>) => void;
  min?: number;
  max?: number;
}

export const MoneyInput = forwardRef<HTMLInputElement, MoneyInputProps>(
  (
    {
      label,
      helperText,
      error,
      value,
      defaultValue,
      placeholder = 'e.g. 5,00,000',
      required,
      disabled,
      id,
      name,
      className,
      onChange,
      onBlur,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const inputId = id || generatedId;
    const helperId = `${inputId}-helper`;
    const errorId = `${inputId}-error`;
    const hasError = Boolean(error);

    const [displayVal, setDisplayVal] = useState<string>(() => {
      const initial = value !== undefined ? value : defaultValue;
      return initial !== undefined && initial !== null ? formatIndianCurrency(initial) : '';
    });

    useEffect(() => {
      if (value !== undefined) {
        setDisplayVal(value !== null && value !== '' ? formatIndianCurrency(value) : '');
      }
    }, [value]);

    const handleChange = (e: ChangeEvent<HTMLInputElement>): void => {
      const rawInput = e.target.value;
      const parsedNum = parseIndianCurrency(rawInput);

      if (parsedNum !== null) {
        setDisplayVal(formatIndianCurrency(parsedNum));
        onChange?.(parsedNum);
      } else {
        setDisplayVal(rawInput.replace(/[^0-9,]/g, ''));
        onChange?.(null);
      }
    };

    const handleBlur = (e: FocusEvent<HTMLInputElement>): void => {
      const parsed = parseIndianCurrency(displayVal);
      if (parsed !== null) {
        setDisplayVal(formatIndianCurrency(parsed));
      } else {
        setDisplayVal('');
      }
      onBlur?.(e);
    };

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={inputId} className="block text-xs font-semibold text-content-primary mb-1.5">
            {label}
            {required && <span className="text-paytm-red ml-1" aria-hidden="true">*</span>}
          </label>
        )}

        <div className="relative flex items-center">
          <div className="absolute left-3 inset-y-0 flex items-center pointer-events-none text-content-secondary font-semibold text-sm">
            ₹
          </div>

          <input
            ref={ref}
            id={inputId}
            name={name}
            type="text"
            inputMode="numeric"
            disabled={disabled}
            value={displayVal}
            placeholder={placeholder}
            onChange={handleChange}
            onBlur={handleBlur}
            aria-invalid={hasError ? 'true' : undefined}
            aria-describedby={hasError ? errorId : helperText ? helperId : undefined}
            className={cn(
              'w-full rounded-button bg-surface border border-surface-border pl-8 pr-3.5 py-2 text-sm text-content-primary font-medium placeholder:text-content-tertiary transition-colors duration-150',
              'focus-visible:ring-2 focus-visible:ring-paytm-cyan focus-visible:border-paytm-cyan focus-visible:outline-none',
              'disabled:bg-surface-muted disabled:text-content-tertiary disabled:cursor-not-allowed',
              hasError && 'border-paytm-red focus-visible:ring-paytm-red focus-visible:border-paytm-red',
              className
            )}
            {...props}
          />
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

MoneyInput.displayName = 'MoneyInput';
export default MoneyInput;
