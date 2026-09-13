import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';

export type JourneyPackDetail = components['schemas']['JourneyPackDetail'];
export type JourneyType = components['schemas']['JourneyType'];

export const usePack = (journeyType: JourneyType | string | undefined) => {
  return useQuery<JourneyPackDetail>({
    queryKey: ['journey-pack', journeyType],
    queryFn: () => apiClient.get<JourneyPackDetail>(`/journey-packs/${journeyType}`),
    enabled: Boolean(journeyType),
  });
};
