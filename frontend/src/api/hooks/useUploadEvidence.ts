import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';

export type EvidenceResponse = components['schemas']['EvidenceResponse'];

export interface UploadEvidencePayload {
  journeyId: string;
  file?: File | null;
  manual_fields?: Record<string, unknown> | string;
  doc_type: string;
  expected_snapshot_id: string;
}

export const useUploadEvidence = () => {
  return useMutation<EvidenceResponse, Error, UploadEvidencePayload>({
    mutationFn: ({ journeyId, file, manual_fields, doc_type, expected_snapshot_id }) => {
      const formData = new FormData();
      if (file) {
        formData.append('file', file);
      }
      if (manual_fields !== undefined) {
        formData.append(
          'manual_fields',
          typeof manual_fields === 'string' ? manual_fields : JSON.stringify(manual_fields)
        );
      }
      formData.append('doc_type', doc_type);
      formData.append('expected_snapshot_id', expected_snapshot_id);

      return apiClient.postForm<EvidenceResponse>(`/journeys/${journeyId}/evidence`, formData);
    },
    onSuccess: () => {
      // Intentionally do nothing with cache here. 
      // /evidence is a preview-only endpoint that does NOT mutate the backend journey.
      // Cache invalidation/updates only happen in useApplyAction.ts.
    },
  });
};
