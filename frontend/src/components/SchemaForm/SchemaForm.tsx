import { useEffect, useMemo, useRef, type ReactElement, type ReactNode } from 'react';
import { useForm, type SubmitHandler } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import type { components } from '@/api/types.gen';
import { cn } from '@/lib/utils';
import { toZodSchema } from './toZodSchema';
import { FieldRenderer } from './FieldRenderer';
import { Button } from '@/components/primitives/Button';

type GoalFieldSpec = components['schemas']['GoalFieldSpec'];

export interface SchemaFormProps {
  schema: GoalFieldSpec[];
  defaultValues?: Record<string, unknown>;
  values?: Record<string, unknown>;
  submitLabel: string;
  onSubmit: (values: Record<string, unknown>) => void | Promise<void>;
  isSubmitting?: boolean;
  serverErrors?: Record<string, string>;
  className?: string;
  children?: ReactNode;
}

export function SchemaForm({
  schema,
  defaultValues,
  values,
  submitLabel,
  onSubmit,
  isSubmitting = false,
  serverErrors,
  className,
  children,
}: SchemaFormProps): ReactElement {
  const zodSchema = useMemo(() => toZodSchema(schema), [schema]);

  const {
    control,
    handleSubmit,
    setValue,
    setError,
    formState: { errors },
  } = useForm<Record<string, unknown>>({
    resolver: zodResolver(zodSchema),
    defaultValues: defaultValues ?? {},
    values: values,
    resetOptions: {
      keepDirtyValues: false,
    },
  });

  // Imperatively synchronize form inputs when values prop changes (e.g. from natural language parsing)
  useEffect(() => {
    if (values && Object.keys(values).length > 0) {
      Object.entries(values).forEach(([key, val]) => {
        if (val !== undefined && val !== null) {
          setValue(key, val, {
            shouldValidate: true,
            shouldDirty: true,
            shouldTouch: true,
          });
        }
      });
    }
  }, [values, setValue]);

  // Inject server-side validation errors when passed
  useEffect(() => {
    if (serverErrors && Object.keys(serverErrors).length > 0) {
      Object.entries(serverErrors).forEach(([key, message]) => {
        setError(key, {
          type: 'server',
          message,
        });
      });
    }
  }, [serverErrors, setError]);

  const isSubmittingRef = useRef(false);
  isSubmittingRef.current = isSubmitting;

  const onValidSubmit: SubmitHandler<Record<string, unknown>> = async (data) => {
    if (isSubmittingRef.current || isSubmitting) return;
    isSubmittingRef.current = true;
    try {
      await onSubmit(data);
    } finally {
      isSubmittingRef.current = false;
    }
  };

  return (
    <form
      onSubmit={handleSubmit(onValidSubmit)}
      noValidate
      className={cn('space-y-6', className)}
    >
      <div className="space-y-4">
        {schema.map((field) => (
          <FieldRenderer
            key={field.key}
            field={field}
            control={control}
            errors={errors}
            disabled={isSubmitting}
          />
        ))}
      </div>

      {children}

      <Button
        type="submit"
        variant="primary"
        size="lg"
        className="w-full"
        isLoading={isSubmitting}
        disabled={isSubmitting}
      >
        {submitLabel}
      </Button>
    </form>
  );
}

export default SchemaForm;
