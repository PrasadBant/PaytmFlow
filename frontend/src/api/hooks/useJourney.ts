import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';

export type JourneyStateResponse = components['schemas']['JourneyStateResponse'] & {
  ui_labels?: Record<string, string>;
  available_actions?: string[];
  resume_screen?: string;
};

export const useJourney = (journeyId: string | undefined) => {
  return useQuery<JourneyStateResponse>({
    queryKey: ['journey', journeyId],
    queryFn: () => apiClient.get<JourneyStateResponse>(`/journeys/${journeyId}`),
    enabled: Boolean(journeyId),
  });
};
