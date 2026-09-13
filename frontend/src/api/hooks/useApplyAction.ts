import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';

export type ActionResponse = components['schemas']['ActionResponse'];

export interface ApplyActionPayload {
  journeyId: string;
  action_id: string;
  expected_snapshot_id: string;
  idempotency_key: string;
  input?: Record<string, unknown>;
}

export const useApplyAction = () => {
  const queryClient = useQueryClient();

  return useMutation<ActionResponse, Error, ApplyActionPayload>({
    mutationFn: ({ journeyId, ...payload }) =>
      apiClient.post<ActionResponse>(`/journeys/${journeyId}/actions`, payload),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(['journey', variables.journeyId], data.journey);
      if (data.next_recommendation) {
        queryClient.setQueryData(['recommendation', variables.journeyId], data.next_recommendation);
      }
      queryClient.invalidateQueries({ queryKey: ['journey', variables.journeyId] });
      queryClient.invalidateQueries({ queryKey: ['recommendation', variables.journeyId] });
      queryClient.invalidateQueries({ queryKey: ['journeys'] });
    },
  });
};
