import { describe, it, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Screen01Home } from '@/screens/Screen01Home';
import { Screen02JourneySelection } from '@/screens/Screen02JourneySelection';
import { Screen03GoalBasicInfo } from '@/screens/Screen03GoalBasicInfo';
import { Screen04CurrentStatus } from '@/screens/Screen04CurrentStatus';
import { Screen05Recommendation } from '@/screens/Screen05Recommendation';
import { Screen06UploadEvidence } from '@/screens/Screen06UploadEvidence';
import { Screen07AiAnalysis } from '@/screens/Screen07AiAnalysis';
import { Screen08UpdatedStatus } from '@/screens/Screen08UpdatedStatus';
import { Screen09CompleteJourney } from '@/screens/Screen09CompleteJourney';
import { Screen10MyJourneys } from '@/screens/Screen10MyJourneys';

const BANNED_PATTERNS = [
  { pattern: /\bapprov/i, name: 'approval / approved' },
  { pattern: /\bprobabilit/i, name: 'probability' },
  { pattern: /\bcredit\s*score\b/i, name: 'credit score' },
  { pattern: /\beligibility\s*score\b/i, name: 'eligibility score' },
  { pattern: /\breadiness\s*score\b/i, name: 'readiness score' },
  { pattern: /\bguarantee/i, name: 'guarantee / guaranteed' },
];

const PERCENTAGE_PATTERN = /\d+\s*%/;

function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

describe('Phase F32: Claim Safety & Prohibited-Claims Audit across Screens 1–10', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  const assertClaimSafety = (screenName: string, container: HTMLElement) => {
    const textContent = container.textContent || '';
    const innerHtml = container.innerHTML;

    // 1. Verify absence of banned words
    for (const { pattern, name } of BANNED_PATTERNS) {
      if (pattern.test(textContent)) {
        throw new Error(
          `[Claim Safety Violation on ${screenName}]: Prohibited word pattern "${name}" was detected in rendered output.`
        );
      }
    }

    // 2. Verify absence of percentage indicators
    if (PERCENTAGE_PATTERN.test(textContent) || PERCENTAGE_PATTERN.test(innerHtml)) {
      throw new Error(
        `[Claim Safety Violation on ${screenName}]: Percentage character '%' was detected in rendered output. Progress must strictly be "X/Y Completed".`
      );
    }
  };

  it('Screen 1 Home: Zero prohibited claims and zero percentage signs', async () => {
    const { container } = render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<Screen01Home />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await screen.findByText(/Your Financial Journey/i);
    assertClaimSafety('Screen 1 (Home)', container);
  });

  it('Screen 2 Selection: Zero prohibited claims and zero percentage signs', async () => {
    const { container } = render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={['/start']}>
          <Routes>
            <Route path="/start" element={<Screen02JourneySelection />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await screen.findByText('Choose Your Financial Journey');
    assertClaimSafety('Screen 2 (Selection)', container);
  });

  it('Screen 3 Goal Form: Zero prohibited claims and zero percentage signs', async () => {
    const { container } = render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={['/start/LENDING']}>
          <Routes>
            <Route path="/start/:type" element={<Screen03GoalBasicInfo />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await screen.findByTestId('screen-03-goal-basic-info');
    assertClaimSafety('Screen 3 (Goal & Basic Info)', container);
  });

  it('Screen 4 Current Status: Zero prohibited claims and zero percentage signs', async () => {
    const { container } = render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={['/j/11111111-1111-1111-1111-111111111111']}>
          <Routes>
            <Route path="/j/:id" element={<Screen04CurrentStatus />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await screen.findByTestId('screen-04-current-status');
    assertClaimSafety('Screen 4 (Current Status)', container);
  });

  it('Screen 5 Recommendation: Zero prohibited claims and zero percentage signs', async () => {
    const { container } = render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={['/j/11111111-1111-1111-1111-111111111111/next']}>
          <Routes>
            <Route path="/j/:id/next" element={<Screen05Recommendation />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await screen.findByTestId('screen-05-recommendation');
    assertClaimSafety('Screen 5 (Recommendation)', container);
  });

  it('Screen 6 Upload Evidence: Zero prohibited claims and zero percentage signs', async () => {
    const { container } = render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter
          initialEntries={['/j/11111111-1111-1111-1111-111111111111/act/UPLOAD_INCOME_PROOF']}
        >
          <Routes>
            <Route path="/j/:id/act/:actionId" element={<Screen06UploadEvidence />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await screen.findByRole('heading', { level: 1 });
    assertClaimSafety('Screen 6 (Upload Evidence)', container);
  });

  it('Screen 7 AI Analysis: Zero prohibited claims and zero percentage signs', async () => {
    const mockEvidenceResponse = {
      evidence_id: 'ev-test-uuid',
      filename: 'payslip.pdf',
      uploaded_at: '2026-09-12T10:05:00Z',
      interpretation: {
        verified: true,
        confidence: 0.96,
        detected: [{ key: 'monthly_income', label: 'Monthly Salary', display_value: '₹85,000' }],
        summary: 'Income verified from August 2026 salary slip.',
        conflicts: [],
      },
      consequence_preview: {
        newly_satisfied: [{ key: 'monthly_income', label: 'Monthly Income' }],
        newly_unlocked: [{ action_id: 'SET_LOAN_TENURE', title: 'Set Loan Tenure' }],
        still_blocked: [],
        predicted_readiness: 'NOT_READY' as const,
        progress_before: { completed: 3, pending: 2, blockers: 2, total: 7 },
        progress_after: { completed: 4, pending: 2, blockers: 1, total: 7 },
      },
      diff_preview: {
        from_version: 1,
        to_version: 2,
        fields_changed: [
          {
            key: 'monthly_income',
            label: 'Monthly Income',
            from_status: 'BLOCKED' as const,
            to_status: 'SATISFIED' as const,
            display_value: '₹85,000',
          },
        ],
        actions_unlocked: ['SET_LOAN_TENURE'],
        actions_removed: ['UPLOAD_INCOME_PROOF'],
        readiness: { from: 'NOT_READY' as const, to: 'NOT_READY' as const },
        progress: {
          from: { completed: 3, pending: 2, blockers: 2, total: 7 },
          to: { completed: 4, pending: 2, blockers: 1, total: 7 },
        },
      },
      requires_review: false,
      proposed_action_id: 'UPLOAD_INCOME_PROOF',
    };

    const { container } = render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter
          initialEntries={[
            {
              pathname: '/j/11111111-1111-1111-1111-111111111111/analysis',
              state: {
                evidenceResponse: mockEvidenceResponse,
                journeyId: '11111111-1111-1111-1111-111111111111',
                snapshotId: '11111111-1111-1111-1111-111111111111',
                actionId: 'UPLOAD_INCOME_PROOF',
              },
            },
          ]}
        >
          <Routes>
            <Route path="/j/:id/analysis" element={<Screen07AiAnalysis />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await screen.findByTestId('screen-07-ai-analysis');
    assertClaimSafety('Screen 7 (AI Analysis)', container);
  });

  it('Screen 8 Updated Status: Zero prohibited claims and zero percentage signs', async () => {
    const mockActionResponse = {
      journey: {
        journey_id: '11111111-1111-1111-1111-111111111111',
        journey_type: 'LENDING' as const,
        schema_version: '1.0.0',
        snapshot_id: '22222222-2222-2222-2222-222222222222',
        version_number: 2,
        readiness: 'NOT_READY' as const,
        status: 'IN_PROGRESS' as const,
        progress: { completed: 4, pending: 2, blockers: 1, total: 7 },
        fields: [],
        display: { title: 'Personal Loan', summary: '₹5,00,000' },
      },
      diff: {
        from_version: 1,
        to_version: 2,
        fields_changed: [
          {
            key: 'monthly_income',
            label: 'Monthly Income',
            from_status: 'BLOCKED' as const,
            to_status: 'SATISFIED' as const,
            display_value: '₹85,000',
          },
        ],
        actions_unlocked: ['SET_LOAN_TENURE'],
        actions_removed: ['UPLOAD_INCOME_PROOF'],
        readiness: { from: 'NOT_READY' as const, to: 'NOT_READY' as const },
        progress: {
          from: { completed: 3, pending: 2, blockers: 2, total: 7 },
          to: { completed: 4, pending: 2, blockers: 1, total: 7 },
        },
      },
    };

    const { container } = render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter
          initialEntries={[
            {
              pathname: '/j/11111111-1111-1111-1111-111111111111/updated',
              state: {
                actionResponse: mockActionResponse,
                journeyId: '11111111-1111-1111-1111-111111111111',
              },
            },
          ]}
        >
          <Routes>
            <Route path="/j/:id/updated" element={<Screen08UpdatedStatus />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await screen.findByTestId('screen-08-updated-status');
    assertClaimSafety('Screen 8 (Updated Status)', container);
  });

  it('Screen 9 Complete Journey: Zero prohibited claims and zero percentage signs', async () => {
    const { container } = render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={['/j/11111111-1111-1111-1111-111111111111/complete']}>
          <Routes>
            <Route path="/j/:id/complete" element={<Screen09CompleteJourney />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await screen.findByTestId('screen-09-complete-journey');
    assertClaimSafety('Screen 9 (Complete Journey)', container);
  });

  it('Screen 10 My Journeys: Zero prohibited claims and zero percentage signs', async () => {
    const { container } = render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={['/my-journeys']}>
          <Routes>
            <Route path="/my-journeys" element={<Screen10MyJourneys />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await screen.findByTestId('screen-10-my-journeys');
    assertClaimSafety('Screen 10 (My Journeys)', container);
  });
});
