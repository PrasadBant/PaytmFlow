import type { ReactElement } from 'react';
import { Select } from '@/components/primitives/Select';
import type { JourneyPackSummary } from '@/api/hooks/usePacks';

export interface GoalSelectorProps {
  currentJourneyType: string;
  packs?: JourneyPackSummary[];
  fallbackDescription?: string;
  onSelectJourneyType: (journeyType: string) => void;
  disabled?: boolean;
}

export function GoalSelector({
  currentJourneyType,
  packs = [],
  fallbackDescription,
  onSelectJourneyType,
  disabled = false,
}: GoalSelectorProps): ReactElement {
  const currentPack = packs.find((p) => p.journey_type === currentJourneyType);
  const displayDescription = currentPack?.description || fallbackDescription;
  const options = packs
    .filter((p) => p.lifecycle_status !== 'DRAFT')
    .map((p) => ({
      value: p.journey_type,
      label: p.display_name,
    }));

  return (
    <div className="mb-5 space-y-1.5" data-testid="goal-selector">
      <label htmlFor="goal-selector-select" className="block text-sm font-semibold text-content-primary">
        I want to
      </label>
      <Select
        id="goal-selector-select"
        value={currentJourneyType}
        options={options.length > 0 ? options : [{ value: currentJourneyType, label: currentJourneyType }]}
        onChange={(e) => onSelectJourneyType(e.target.value)}
        disabled={disabled}
        className="font-medium text-content-primary bg-surface border-surface-border shadow-xs"
        aria-label="I want to select goal journey"
      />
      {displayDescription && (
        <p className="text-xs sm:text-sm text-content-secondary mt-1">
          {displayDescription}
        </p>
      )}
    </div>
  );
}

export default GoalSelector;
