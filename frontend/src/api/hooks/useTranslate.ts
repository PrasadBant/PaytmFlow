import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';

export type TranslateResponse = components['schemas']['TranslateResponse'];

export interface TranslatePayload {
  text: string;
  targetLanguageCode: string;
}

// Scoped to ONE already-generated free-text string per call (Sarvam
// Mayura) - never a whole API response. Callers must only ever pass
// already-rendered explanation/chat text, never a display_value, amount,
// or status field.
export const useTranslateText = () => {
  return useMutation<TranslateResponse, Error, TranslatePayload>({
    mutationFn: ({ text, targetLanguageCode }) =>
      apiClient.post<TranslateResponse>('/translate', {
        text,
        target_language_code: targetLanguageCode,
      }),
  });
};
