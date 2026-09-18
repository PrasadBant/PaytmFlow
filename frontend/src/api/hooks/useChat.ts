import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';

export type ChatResponse = components['schemas']['ChatResponse'];

export interface ChatPayload {
  journeyId: string;
  message: string;
}

export const useChat = () => {
  return useMutation<ChatResponse, Error, ChatPayload>({
    mutationFn: ({ journeyId, message }) =>
      apiClient.post<ChatResponse>(`/journeys/${journeyId}/chat`, { message }),
  });
};

/** For screens with no journey yet (e.g. the goal-creation form) - still a
 * real LLM call, just with no journey_state/recommendation to ground on. */
export const useGeneralChat = () => {
  return useMutation<ChatResponse, Error, string>({
    mutationFn: (message) => apiClient.post<ChatResponse>('/chat', { message }),
  });
};
