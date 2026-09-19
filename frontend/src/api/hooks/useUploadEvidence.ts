import { useMutation, useQueryClient } from '@tanstack/react-query';
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
  const queryClient = useQueryClient();
  
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
    onSuccess: (_, variables) => {
      // Invalidate the review status because an upload might clear an ADDITIONAL_INFO_REQUIRED block.
      queryClient.invalidateQueries({ queryKey: ['journey-review-status', variables.journeyId] });
      // We also invalidate the journey state just in case, though the preview usually drives UI updates.
      queryClient.invalidateQueries({ queryKey: ['journey', variables.journeyId] });
    },
  });
};
