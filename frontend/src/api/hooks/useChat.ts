import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';

export type ChatResponse = components['schemas']['ChatResponse'];
export type VoiceChatResponse = components['schemas']['VoiceChatResponse'];

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

export interface VoiceChatPayload {
  journeyId: string;
  audioBlob: Blob;
}

/** Voice is an input modality, not a shortcut: the backend transcribes
 * (Sarvam Saaras) and answers through the SAME grounded chat() path
 * useChat already uses. Not available before a journey exists. */
export const useVoiceChat = () => {
  return useMutation<VoiceChatResponse, Error, VoiceChatPayload>({
    mutationFn: ({ journeyId, audioBlob }) => {
      const form = new FormData();
      form.append('file', audioBlob, 'voice-message.webm');
      return apiClient.postForm<VoiceChatResponse>(`/journeys/${journeyId}/chat/voice`, form);
    },
  });
};

/** For screens with no journey yet (e.g. the goal-creation form) - still a
 * real LLM call, just with no journey_state/recommendation to ground on. */
export const useGeneralChat = () => {
  return useMutation<ChatResponse, Error, string>({
    mutationFn: (message) => apiClient.post<ChatResponse>('/chat', { message }),
  });
};
