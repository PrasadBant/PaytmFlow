import { useState, type ReactElement } from 'react';
import { AlertCircle } from 'lucide-react';
import { Modal } from '@/components/primitives/Modal';
import { SchemaForm } from '@/components/SchemaForm';
import { useApplyAction, type ActionResponse } from '@/api/hooks/useApplyAction';
import { ApiError } from '@/api/errors';
import type { components } from '@/api/types.gen';

export type ActionOption = components['schemas']['ActionOption'];

export interface FormActionModalProps {
  isOpen: boolean;
  onClose: () => void;
  action: ActionOption | null;
  journeyId: string;
  expectedSnapshotId: string;
  defaultValues?: Record<string, unknown>;
  onSuccess?: (response: ActionResponse) => void;
}

export function FormActionModal({
  isOpen,
  onClose,
  action,
  journeyId,
  expectedSnapshotId,
  defaultValues,
  onSuccess,
}: FormActionModalProps): ReactElement | null {
  const applyAction = useApplyAction();
  const [serverErrors, setServerErrors] = useState<Record<string, string> | undefined>(undefined);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen || !action) return null;

  const handleSubmit = async (values: Record<string, unknown>): Promise<void> => {
    if (isSubmitting || applyAction.isPending) return;
    setIsSubmitting(true);
    setErrorMessage(null);
    setServerErrors(undefined);

    const idempotencyKey =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : '00000000-0000-4000-8000-' + Math.random().toString(36).substring(2, 14);

    try {
      const response = await applyAction.mutateAsync({
        journeyId,
        action_id: action.action_id,
        expected_snapshot_id: expectedSnapshotId,
        idempotency_key: idempotencyKey,
        input: values,
      });

      onClose();
      onSuccess?.(response);
    } catch (err) {
      setIsSubmitting(false);
      if (err instanceof ApiError) {
        if (err.details) {
          const fieldErrors: Record<string, string> = {};
          Object.entries(err.details).forEach(([k, v]) => {
            fieldErrors[k] = typeof v === 'string' ? v : JSON.stringify(v);
          });
          setServerErrors(fieldErrors);
        }
        setErrorMessage(err.message || 'Action submission failed. Please verify your inputs.');
      } else {
        setErrorMessage('An unexpected error occurred. Please try again.');
      }
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={action.title}
      description={action.why}
      size="md"
    >
      <div className="space-y-4">
        {errorMessage && (
          <div
            data-testid="form-action-error"
            className="p-3.5 rounded-card bg-paytm-red-light border border-red-200 text-paytm-red-dark text-xs flex items-start gap-2.5"
          >
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-paytm-red" />
            <span>{errorMessage}</span>
          </div>
        )}

        <SchemaForm
          schema={action.input_schema || []}
          submitLabel="Submit Changes →"
          onSubmit={handleSubmit}
          isSubmitting={isSubmitting || applyAction.isPending}
          serverErrors={serverErrors}
          defaultValues={defaultValues}
        />
      </div>
    </Modal>
  );
}

export default FormActionModal;
