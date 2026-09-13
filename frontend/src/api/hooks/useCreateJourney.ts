import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';

export type JourneyType = components['schemas']['JourneyType'];
export type JourneyStateResponse = components['schemas']['JourneyStateResponse'];

export interface CreateJourneyPayload {
  journey_type: JourneyType;
  goal: Record<string, unknown>;
  natural_language?: string;
}

export const useCreateJourney = () => {
  const queryClient = useQueryClient();

  return useMutation<JourneyStateResponse, Error, CreateJourneyPayload>({
    mutationFn: (payload) => apiClient.post<JourneyStateResponse>('/journeys', payload),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['journeys'] });
      queryClient.setQueryData(['journey', data.journey_id], data);
    },
  });
};
