import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';

export type ActionResponse = components['schemas']['ActionResponse'];

export interface SubmitClarificationPayload {
  journeyId: string;
  ambiguity_id: string;
  field: string;
  answer: unknown;
  expected_snapshot_id: string;
}

export const useClarification = () => {
  const queryClient = useQueryClient();

  return useMutation<ActionResponse, Error, SubmitClarificationPayload>({
    mutationFn: ({ journeyId, ...payload }) =>
      apiClient.post<ActionResponse>(`/journeys/${journeyId}/clarifications`, payload),
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
