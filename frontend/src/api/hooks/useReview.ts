import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../client';
import type { components } from '../types.gen';
import { useRoleStore } from '../../state/role';

export type Role = components['schemas']['ReviewerRole'];
export type ReviewCase = components['schemas']['ReviewCase'];
export type ReviewCaseDetail = components['schemas']['ReviewCaseDetail'];
export type ReviewCaseStatus = components['schemas']['ReviewCaseStatus'];
export type ReviewResolutionType = components['schemas']['ReviewResolutionType'];
export type ReviewDashboardMetrics = components['schemas']['ReviewDashboardMetrics'];
export type ReviewCaseAuditEntry = components['schemas']['ReviewCaseAuditEntry'];
export type CustomerReviewStatus = components['schemas']['CustomerReviewStatus'];

export interface ReviewQueueFilters {
  status?: ReviewCaseStatus;
  priority?: string;
  journey_type?: string;
  mine?: boolean;
}

export const useSwitchRole = () => {
  const queryClient = useQueryClient();
  const setRole = useRoleStore((s) => s.setRole);
  return useMutation<{ role: Role }, Error, Role>({
    mutationFn: (role) => apiClient.post<{ role: Role }>('/review/role', { role }),
    onSuccess: (data) => {
      setRole(data.role);
      queryClient.invalidateQueries({ queryKey: ['review'] });
    },
  });
};

export const useReviewDashboard = () => {
  return useQuery<ReviewDashboardMetrics>({
    queryKey: ['review', 'dashboard'],
    queryFn: () => apiClient.get<ReviewDashboardMetrics>('/review/dashboard'),
  });
};

export const useReviewQueue = (filters?: ReviewQueueFilters) => {
  return useQuery<{ cases: ReviewCase[] }>({
    queryKey: ['review', 'queue', filters],
    queryFn: () =>
      apiClient.get<{ cases: ReviewCase[] }>('/review/cases', {
        params: filters as Record<string, string | number | boolean | undefined | null>,
      }),
  });
};

export const useReviewCase = (caseId: string | undefined) => {
  return useQuery<ReviewCaseDetail>({
    queryKey: ['review', 'case', caseId],
    queryFn: () => apiClient.get<ReviewCaseDetail>(`/review/cases/${caseId}`),
    enabled: !!caseId,
  });
};

export const useReviewCaseAudit = (caseId: string | undefined) => {
  return useQuery<{ entries: ReviewCaseAuditEntry[] }>({
    queryKey: ['review', 'case', caseId, 'audit'],
    queryFn: () =>
      apiClient.get<{ entries: ReviewCaseAuditEntry[] }>(`/review/cases/${caseId}/audit`),
    enabled: !!caseId,
  });
};

function invalidateCase(queryClient: ReturnType<typeof useQueryClient>, caseId: string) {
  queryClient.invalidateQueries({ queryKey: ['review', 'case', caseId] });
  queryClient.invalidateQueries({ queryKey: ['review', 'queue'] });
  queryClient.invalidateQueries({ queryKey: ['review', 'dashboard'] });
}

export const useClaimCase = () => {
  const queryClient = useQueryClient();
  return useMutation<
    ReviewCase,
    Error,
    { caseId: string; expected_case_version: number }
  >({
    mutationFn: ({ caseId, expected_case_version }) =>
      apiClient.post<ReviewCase>(`/review/cases/${caseId}/claim`, { expected_case_version }),
    onSuccess: (_data, variables) => invalidateCase(queryClient, variables.caseId),
  });
};

export interface ResolveCasePayload {
  caseId: string;
  resolution_type: ReviewResolutionType;
  resolution_reason: string;
  resolution_notes?: string;
  resolution_value?: unknown;
  expected_case_version: number;
}

export const useResolveCase = () => {
  const queryClient = useQueryClient();
  return useMutation<ReviewCaseDetail, Error, ResolveCasePayload>({
    mutationFn: ({ caseId, ...payload }) =>
      apiClient.post<ReviewCaseDetail>(`/review/cases/${caseId}/resolve`, payload),
    onSuccess: (_data, variables) => invalidateCase(queryClient, variables.caseId),
  });
};

export interface RequestInformationPayload {
  caseId: string;
  requested_docs: string[];
  customer_message: string;
  expected_case_version: number;
}

export const useRequestInformation = () => {
  const queryClient = useQueryClient();
  return useMutation<ReviewCase, Error, RequestInformationPayload>({
    mutationFn: ({ caseId, ...payload }) =>
      apiClient.post<ReviewCase>(`/review/cases/${caseId}/request-information`, payload),
    onSuccess: (_data, variables) => invalidateCase(queryClient, variables.caseId),
  });
};

export interface EscalateCasePayload {
  caseId: string;
  escalation_reason: string;
  expected_case_version: number;
}

export const useEscalateCase = () => {
  const queryClient = useQueryClient();
  return useMutation<ReviewCase, Error, EscalateCasePayload>({
    mutationFn: ({ caseId, ...payload }) =>
      apiClient.post<ReviewCase>(`/review/cases/${caseId}/escalate`, payload),
    onSuccess: (_data, variables) => invalidateCase(queryClient, variables.caseId),
  });
};

export const useJourneyReviewStatus = (journeyId: string | undefined) => {
  return useQuery<CustomerReviewStatus>({
    queryKey: ['journey-review-status', journeyId],
    queryFn: () =>
      apiClient.get<CustomerReviewStatus>(`/journeys/${journeyId}/review-status`),
    enabled: !!journeyId,
  });
};
