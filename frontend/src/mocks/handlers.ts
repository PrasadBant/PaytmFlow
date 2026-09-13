import { http, HttpResponse, delay } from 'msw';
import { getActiveScenario } from './scenarios';

// Fixture imports from frontend/src/mocks/fixtures (isolated frontend mock layer)
import sessionFixture from './fixtures/session.json';
import packsListFixture from './fixtures/packs.list.json';
import packsLendingFixture from './fixtures/packs.LENDING.json';
import packsInsuranceFixture from './fixtures/packs.INSURANCE.json';
import packsCreditCardFixture from './fixtures/packs.CREDIT_CARD.json';
import packsKycFixture from './fixtures/packs.KYC.json';
import packsAccountOpeningFixture from './fixtures/packs.ACCOUNT_OPENING.json';
import packsInvestmentFixture from './fixtures/packs.INVESTMENT.json';

import lendingV1State from './fixtures/lending/v1.state.json';
import lendingV1Recommendation from './fixtures/lending/v1.recommendation.json';
import lendingEvidenceSalarySlip from './fixtures/lending/evidence.salary_slip.json';
import lendingV2Action from './fixtures/lending/v2.action.json';
import lendingV3Recommendation from './fixtures/lending/v3.recommendation.json';
import lendingEvidenceBankStatement from './fixtures/lending/evidence.bank_statement.json';
import lendingV4Clarification from './fixtures/lending/v4.clarification.json';
import lendingV5Ready from './fixtures/lending/v5.ready.json';
import lendingErrorStale from './fixtures/lending/error.stale.json';
import lendingErrorInvalid from './fixtures/lending/error.invalid.json';
import lendingErrorDeadend from './fixtures/lending/error.deadend.json';

import insuranceV1State from './fixtures/insurance/v1.state.json';
import kycV1State from './fixtures/kyc/v1.state.json';
import creditCardV1State from './fixtures/credit_card/v1.state.json';
import accountOpeningV1State from './fixtures/account_opening/v1.state.json';
import investmentV1State from './fixtures/investment/v1.state.json';

import journeysListFixture from './fixtures/journeys.list.json';

const packDetailsMap: Record<string, unknown> = {
  LENDING: packsLendingFixture,
  INSURANCE: packsInsuranceFixture,
  CREDIT_CARD: packsCreditCardFixture,
  KYC: packsKycFixture,
  ACCOUNT_OPENING: packsAccountOpeningFixture,
  INVESTMENT: packsInvestmentFixture,
};

const packInitialStates: Record<string, unknown> = {
  LENDING: lendingV1State,
  INSURANCE: insuranceV1State,
  KYC: kycV1State,
  CREDIT_CARD: creditCardV1State,
  ACCOUNT_OPENING: accountOpeningV1State,
  INVESTMENT: investmentV1State,
};

// State tracker for Lending sequence walk
let currentLendingStep = 1;

export function resetMockState(): void {
  currentLendingStep = 1;
}

export function setLendingStep(step: number): void {
  currentLendingStep = step;
}

export const handlers = [
  // 1. GET /api/v1/health
  http.get('*/api/v1/health', async ({ request }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    return HttpResponse.json({
      status: 'ok',
      db: true,
      packs_loaded: 6,
      packs_supported: 6,
      ai_provider: 'mock',
      git_sha: 'dev1-independent-build',
    });
  }),

  // 2. GET /api/v1/session
  http.get('*/api/v1/session', async ({ request }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    return HttpResponse.json(sessionFixture, {
      headers: {
        'Set-Cookie': 'pf_session=00000000-0000-0000-0000-000000000001; Path=/; HttpOnly; SameSite=Lax',
      },
    });
  }),

  // 3. GET /api/v1/journey-packs
  http.get('*/api/v1/journey-packs', async ({ request }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    return HttpResponse.json(packsListFixture);
  }),

  // 4. GET /api/v1/journey-packs/:journey_type
  http.get('*/api/v1/journey-packs/:journey_type', async ({ params, request }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    const type = String(params.journey_type).toUpperCase();
    const pack = packDetailsMap[type];

    if (!pack) {
      return HttpResponse.json(
        {
          error: {
            code: 'INVALID_JOURNEY_TYPE',
            message: `Journey type '${type}' is not supported.`,
          },
        },
        { status: 400 }
      );
    }

    return HttpResponse.json(pack);
  }),

  // 5. GET /api/v1/journeys (Screen 10)
  http.get('*/api/v1/journeys', async ({ request }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    if (scenario === 'empty') {
      return HttpResponse.json({ journeys: [] });
    }

    return HttpResponse.json(journeysListFixture);
  }),

  // 6. POST /api/v1/journeys (Create Journey)
  http.post('*/api/v1/journeys', async ({ request }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    const body = (await request.json()) as { journey_type?: string; goal?: Record<string, unknown> };
    const type = (body?.journey_type || 'LENDING').toUpperCase();

    if (!packDetailsMap[type]) {
      return HttpResponse.json(
        {
          error: {
            code: 'INVALID_JOURNEY_TYPE',
            message: `Unknown journey type: ${type}`,
          },
        },
        { status: 400 }
      );
    }

    const initialState = packInitialStates[type] || lendingV1State;
    currentLendingStep = 1;

    return HttpResponse.json(initialState, { status: 201 });
  }),

  // 7. GET /api/v1/journeys/:journey_id (Screen 4)
  http.get('*/api/v1/journeys/:journey_id', async ({ request }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    if (scenario === 'deadend') {
      return HttpResponse.json(lendingErrorDeadend);
    }

    if (currentLendingStep >= 5) {
      return HttpResponse.json(lendingV5Ready);
    }
    if (currentLendingStep >= 4) {
      return HttpResponse.json(lendingV4Clarification.journey);
    }
    if (currentLendingStep >= 2) {
      return HttpResponse.json(lendingV2Action.journey);
    }

    return HttpResponse.json(lendingV1State);
  }),

  // 8. GET /api/v1/journeys/:journey_id/recommendation (Screen 5)
  http.get('*/api/v1/journeys/:journey_id/recommendation', async ({ request }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    if (scenario === 'deadend') {
      return HttpResponse.json({
        snapshot_id: lendingErrorDeadend.snapshot_id,
        readiness: 'DEAD_END',
        recommendation: null,
        alternatives: [],
        minimum_path_length: 0,
        source: 'AI_RANKED',
      });
    }

    if (scenario === 'aitimeout') {
      return HttpResponse.json({
        ...lendingV1Recommendation,
        source: 'PLANNER_FALLBACK',
        recommendation: {
          ...lendingV1Recommendation.recommendation,
          why: '',
        },
      });
    }

    if (currentLendingStep >= 5) {
      return HttpResponse.json({
        snapshot_id: lendingV5Ready.snapshot_id,
        readiness: 'READY',
        recommendation: null,
        alternatives: [],
        minimum_path_length: 0,
        source: 'AI_RANKED',
      });
    }

    if (currentLendingStep >= 4) {
      return HttpResponse.json(lendingV4Clarification.next_recommendation);
    }

    if (currentLendingStep >= 2) {
      return HttpResponse.json(lendingV3Recommendation);
    }

    return HttpResponse.json(lendingV1Recommendation);
  }),

  // 9. POST /api/v1/journeys/:journey_id/evidence (Screen 6 -> 7 Preview)
  http.post('*/api/v1/journeys/:journey_id/evidence', async ({ request }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    if (scenario === 'needsreview') {
      return HttpResponse.json(lendingEvidenceBankStatement);
    }

    return HttpResponse.json(lendingEvidenceSalarySlip);
  }),

  // 10. POST /api/v1/journeys/:journey_id/actions (Action Mutation)
  http.post('*/api/v1/journeys/:journey_id/actions', async ({ request }) => {
    const scenario = getActiveScenario(request.url, request);
    if (scenario === 'slow') await delay(1000);

    if (scenario === 'stale') {
      return HttpResponse.json(lendingErrorStale, { status: 409 });
    }

    if (scenario === 'invalid') {
      return HttpResponse.json(lendingErrorInvalid, { status: 422 });
    }

    // Advance step in sequence
    if (currentLendingStep === 1) {
      currentLendingStep = 2;
      return HttpResponse.json(lendingV2Action);
    }

    if (currentLendingStep === 2 || currentLendingStep === 3) {
      currentLendingStep = 4;
      return HttpResponse.json(lendingV4Clarification);
    }

    currentLendingStep = 5;
    return HttpResponse.json({
      journey: lendingV5Ready,
      diff: lendingV4Clarification.diff,
      next_recommendation: null,
    });
  }),

  // 11. POST /api/v1/journeys/:journey_id/clarifications (Needs Review Resolution)
  http.post('*/api/v1/journeys/:journey_id/clarifications', async ({ request }) => {
    const scenario = getActiveScenario(request.url, request);
    if (scenario === 'slow') await delay(1000);

    if (scenario === 'stale') {
      return HttpResponse.json(lendingErrorStale, { status: 409 });
    }

    currentLendingStep = 4;
    return HttpResponse.json(lendingV4Clarification);
  }),

  // 12. GET /api/v1/journeys/:journey_id/diff
  http.get('*/api/v1/journeys/:journey_id/diff', async ({ request }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    return HttpResponse.json(lendingV2Action.diff);
  }),

  // 13. POST /api/v1/demo/reset
  http.post('*/api/v1/demo/reset', async () => {
    currentLendingStep = 1;
    return HttpResponse.json({ reset: true, elapsed_ms: 12 });
  }),
];
