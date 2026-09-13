import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';

export type RecommendationResponse = components['schemas']['RecommendationResponse'];
export type ActionOption = components['schemas']['ActionOption'];

export const useRecommendation = (journeyId: string | undefined) => {
  return useQuery<RecommendationResponse>({
    queryKey: ['recommendation', journeyId],
    queryFn: () => apiClient.get<RecommendationResponse>(`/journeys/${journeyId}/recommendation`),
    enabled: Boolean(journeyId),
  });
};
