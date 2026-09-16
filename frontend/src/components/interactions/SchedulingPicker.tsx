import { useState, type ReactElement } from 'react';
import { Calendar, Clock } from 'lucide-react';
import { Button } from '@/components/primitives/Button';
import { cn } from '@/lib/utils';

export interface SchedulingPickerProps {
  actionTitle: string;
  why?: string | null;
  /** The payload key the backend actually expects for this action's
   * submitted value - the caller must derive this from the action's own
   * `input_schema[0].key` when declared, falling back to
   * `ActionOption.unlocks[0]` (the state field this action resolves) only
   * when no input_schema exists. Passing `unlocks[0]` unconditionally was
   * a real, user-reported bug (BUG-003) whenever an action declared an
   * input_schema key different from what it satisfies - see
   * Screen06UploadEvidence.tsx's `interactionFieldKey`. */
  fieldKey?: string | null;
  submitLabel: string;
  isSubmitting?: boolean;
  onSubmit: (values: Record<string, unknown>) => void | Promise<void>;
}

// A deterministic, generic set of slots relative to "now" - no external
// calendar/scheduling provider exists in this prototype, so the options are
// computed client-side rather than fabricated as fixed fixture strings. Any
// SCHEDULE_* action on any pack gets the same reusable picker.
function buildSlots(): { id: string; label: string; day: string }[] {
  const now = new Date();
  const dayLabel = (offsetDays: number): string => {
    const d = new Date(now);
    d.setDate(d.getDate() + offsetDays);
    return d.toLocaleDateString('en-IN', { weekday: 'long', month: 'short', day: 'numeric' });
  };
  return [
    { id: 'tomorrow-morning', day: dayLabel(1), label: '10:00 AM – 12:00 PM' },
    { id: 'tomorrow-afternoon', day: dayLabel(1), label: '2:00 PM – 4:00 PM' },
    { id: 'dayafter-morning', day: dayLabel(2), label: '10:00 AM – 12:00 PM' },
    { id: 'dayafter-afternoon', day: dayLabel(2), label: '2:00 PM – 4:00 PM' },
  ];
}

export function SchedulingPicker({
  actionTitle,
  why,
  fieldKey,
  submitLabel,
  isSubmitting = false,
  onSubmit,
}: SchedulingPickerProps): ReactElement {
  const [slots] = useState(buildSlots);
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <div data-testid="scheduling-picker" className="space-y-5">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-full bg-paytm-blue-50 text-paytm-blue flex items-center justify-center shrink-0">
          <Calendar className="w-5 h-5" />
        </div>
        <div className="space-y-1">
          <h2 className="text-base font-semibold text-content-primary">{actionTitle}</h2>
          <p className="text-xs text-content-secondary leading-relaxed">
            {why || 'Choose a time slot that works for you.'}
          </p>
        </div>
      </div>

      {/* No separate aria-label here: a <legend> already gives the fieldset
          its accessible name natively. Adding aria-label too would make a
          screen reader announce different text than what's visible - the
          two must never drift apart. */}
      <fieldset className="space-y-2">
        <legend className="text-xs font-bold uppercase tracking-wider text-content-tertiary mb-2">
          Select a time slot
        </legend>
        {slots.map((slot) => {
          const isSelected = selected === slot.id;
          return (
            <label
              key={slot.id}
              className={cn(
                'flex items-center gap-3 p-3.5 rounded-card border cursor-pointer transition-colors',
                isSelected
                  ? 'border-paytm-blue bg-paytm-blue-50'
                  : 'border-surface-border bg-white hover:bg-surface-subtle'
              )}
            >
              <input
                type="radio"
                name="preferred_slot"
                value={slot.id}
                checked={isSelected}
                onChange={() => setSelected(slot.id)}
                className="w-4 h-4 accent-paytm-blue shrink-0"
              />
              <Clock className="w-4 h-4 text-content-tertiary shrink-0" aria-hidden="true" />
              <span className="text-sm text-content-primary">
                <span className="font-semibold">{slot.day}</span>
                <span className="text-content-secondary">, {slot.label}</span>
              </span>
            </label>
          );
        })}
      </fieldset>

      <Button
        type="button"
        variant="primary"
        size="lg"
        className="w-full"
        disabled={!selected || isSubmitting}
        isLoading={isSubmitting}
        onClick={() => {
          if (!selected) return;
          const slot = slots.find((s) => s.id === selected);
          void onSubmit({ [fieldKey || 'preferred_slot']: `${slot?.day}, ${slot?.label}` });
        }}
        data-testid="scheduling-confirm-btn"
      >
        {submitLabel}
      </Button>
    </div>
  );
}

export default SchedulingPicker;
