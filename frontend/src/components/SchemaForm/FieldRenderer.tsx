import type { ReactElement } from 'react';
import { Controller, type Control, type FieldErrors } from 'react-hook-form';
import type { components } from '@/api/types.gen';
import { Input } from '@/components/primitives/Input';
import { Select } from '@/components/primitives/Select';
import { MoneyInput } from '@/components/primitives/MoneyInput';
import { AlertCircle } from 'lucide-react';

type GoalFieldSpec = components['schemas']['GoalFieldSpec'];

export interface FieldRendererProps {
  field: GoalFieldSpec;
  control: Control<Record<string, unknown>>;
  errors: FieldErrors<Record<string, unknown>>;
  disabled?: boolean;
}

export function FieldRenderer({
  field,
  control,
  errors,
  disabled = false,
}: FieldRendererProps): ReactElement {
  const errorObj = errors[field.key];
  const errorMessage = errorObj?.message ? String(errorObj.message) : undefined;
  const fieldId = `field-${field.key}`;

  switch (field.type) {
    case 'enum': {
      const options =
        field.options?.map((opt) =>
          typeof opt === 'string' ? { value: opt, label: opt } : { value: String(opt.value), label: opt.label }
        ) || [];

      return (
        <Controller
          name={field.key}
          control={control}
          render={({ field: formField }) => (
            <Select
              id={fieldId}
              name={field.key}
              label={field.label}
              helperText={field.help_text}
              required={field.required}
              placeholder={field.placeholder || 'Select an option'}
              options={options}
              value={(formField.value as string) ?? ''}
              onChange={(e) => formField.onChange(e.target.value)}
              onBlur={formField.onBlur}
              error={errorMessage}
              disabled={disabled}
            />
          )}
        />
      );
    }

    case 'money': {
      return (
        <Controller
          name={field.key}
          control={control}
          render={({ field: formField }) => (
            <MoneyInput
              id={fieldId}
              name={field.key}
              label={field.label}
              helperText={field.help_text}
              required={field.required}
              placeholder={field.placeholder || 'e.g. 5,00,000'}
              min={field.min}
              max={field.max}
              value={formField.value as number | undefined}
              onChange={(val) => formField.onChange(val ?? undefined)}
              onBlur={formField.onBlur}
              error={errorMessage}
              disabled={disabled}
            />
          )}
        />
      );
    }

    case 'number': {
      return (
        <Controller
          name={field.key}
          control={control}
          render={({ field: formField }) => (
            <Input
              id={fieldId}
              name={field.key}
              type="number"
              label={field.label}
              helperText={field.help_text}
              required={field.required}
              placeholder={field.placeholder}
              min={field.min}
              max={field.max}
              value={(formField.value as string | number) ?? ''}
              onChange={(e) => {
                const val = e.target.value;
                formField.onChange(val === '' ? undefined : Number(val));
              }}
              onBlur={formField.onBlur}
              error={errorMessage}
              disabled={disabled}
            />
          )}
        />
      );
    }

    case 'date': {
      return (
        <Controller
          name={field.key}
          control={control}
          render={({ field: formField }) => (
            <Input
              id={fieldId}
              name={field.key}
              type="date"
              label={field.label}
              helperText={field.help_text}
              required={field.required}
              placeholder={field.placeholder}
              value={(formField.value as string) ?? ''}
              onChange={(e) => formField.onChange(e.target.value)}
              onBlur={formField.onBlur}
              error={errorMessage}
              disabled={disabled}
            />
          )}
        />
      );
    }

    case 'boolean': {
      return (
        <Controller
          name={field.key}
          control={control}
          render={({ field: formField }) => {
            const helperId = `${fieldId}-helper`;
            const errorId = `${fieldId}-error`;
            const hasError = Boolean(errorMessage);

            return (
              <div className="w-full">
                <label
                  htmlFor={fieldId}
                  className="flex items-start gap-3 cursor-pointer select-none group"
                >
                  <input
                    type="checkbox"
                    id={fieldId}
                    name={field.key}
                    checked={Boolean(formField.value)}
                    onChange={(e) => formField.onChange(e.target.checked)}
                    onBlur={formField.onBlur}
                    disabled={disabled}
                    aria-invalid={hasError ? 'true' : undefined}
                    aria-describedby={hasError ? errorId : field.help_text ? helperId : undefined}
                    className="mt-0.5 h-4 w-4 rounded border-surface-border text-paytm-blue focus:ring-2 focus:ring-paytm-cyan focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  />
                  <span className="text-sm font-medium text-content-primary leading-tight">
                    {field.label}
                    {field.required && <span className="text-paytm-red ml-1" aria-hidden="true">*</span>}
                  </span>
                </label>
                {hasError ? (
                  <p id={errorId} className="mt-1.5 text-xs text-paytm-red flex items-center gap-1">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                    <span>{errorMessage}</span>
                  </p>
                ) : field.help_text ? (
                  <p id={helperId} className="mt-1.5 text-xs text-content-secondary pl-7">
                    {field.help_text}
                  </p>
                ) : null}
              </div>
            );
          }}
        />
      );
    }

    case 'text':
    default: {
      return (
        <Controller
          name={field.key}
          control={control}
          render={({ field: formField }) => (
            <Input
              id={fieldId}
              name={field.key}
              type="text"
              label={field.label}
              helperText={field.help_text}
              required={field.required}
              placeholder={field.placeholder}
              value={(formField.value as string) ?? ''}
              onChange={(e) => formField.onChange(e.target.value)}
              onBlur={formField.onBlur}
              error={errorMessage}
              disabled={disabled}
            />
          )}
        />
      );
    }
  }
}
export default FieldRenderer;
