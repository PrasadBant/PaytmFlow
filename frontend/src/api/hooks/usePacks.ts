import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';

export type JourneyPackSummary = components['schemas']['JourneyPackSummary'];
export type JourneyPackListResponse = {
  packs: components['schemas']['JourneyPackSummary'][];
};

export const usePacks = () => {
  return useQuery<JourneyPackListResponse>({
    queryKey: ['journey-packs'],
    queryFn: () => apiClient.get<JourneyPackListResponse>('/journey-packs'),
  });
};
