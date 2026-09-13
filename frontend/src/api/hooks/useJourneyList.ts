import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';

export type JourneyListItem = components['schemas']['JourneyListItem'];
export type JourneyStatus = components['schemas']['JourneyStatus'];
export type JourneyType = components['schemas']['JourneyType'];

export interface JourneyListFilters {
  status?: JourneyStatus;
  journey_type?: JourneyType;
  limit?: number;
}

export interface JourneyListResponse {
  journeys: JourneyListItem[];
}

export const useJourneyList = (filters?: JourneyListFilters) => {
  return useQuery<JourneyListResponse>({
    queryKey: ['journeys', filters],
    queryFn: () =>
      apiClient.get<JourneyListResponse>('/journeys', {
        params: filters as Record<string, string | number | boolean | undefined | null>,
      }),
  });
};
