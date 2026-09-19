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
import lendingEvidenceBankStatementVerified from './fixtures/lending/evidence.bank_statement_verified.json';
import lendingEvidenceAddressProof from './fixtures/lending/evidence.address_proof.json';
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
import reviewCaseDemoFixture from './fixtures/review/case.PF-DEMO-1024.json';

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

// The one journey with a rich, hand-authored multi-step narrative (v1..v5
// fixtures with real copy, conflicts, etc.) - its progression is driven by
// `currentLendingStep` exactly as before. Every other journey - any other
// pack, and any OTHER instance of these packs a user might create - is driven
// generically by `journeyStore` below, keyed by the real journey_id from the
// request. This is the fix for the root-cause bug: previously every mutating
// endpoint ignored `journey_id` entirely and always returned LENDING data,
// so a fresh page load, refresh, deep link, or "Resume" for ANY other
// journey silently showed someone else's fields, blockers and progress.
const LENDING_JOURNEY_ID = '11111111-1111-1111-1111-111111111111';

// State tracker for the Lending sequence walk (unchanged behaviour).
let currentLendingStep = 1;

type MockField = {
  key: string;
  label: string;
  status: string;
  value?: unknown;
  display_value?: string;
  explanation?: string | null;
  resolve_action_id?: string | null;
  mandatory?: boolean;
  ambiguity?: unknown;
};
type MockProgress = { completed: number; pending: number; blockers: number; total: number };
type MockJourney = {
  journey_id: string;
  journey_type: string;
  version_number: number;
  snapshot_id: string;
  readiness: string;
  status: string;
  progress: MockProgress;
  fields: MockField[];
  [key: string]: unknown;
};

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function randomId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

// Per-journey state for every pack other than the LENDING flagship demo,
// keyed by real journey_id. Seeded fresh from each pack's own v1.state
// fixture (never the same object reference the fixture module exports, so
// mutations here can never leak back into the imported JSON or into another
// test's copy of it).
const journeyStore = new Map<string, MockJourney>();
// Last computed diff per journey_id, for GET /journeys/:id/diff - this
// endpoint previously always returned the Lending v2 diff regardless of
// which journey (or even action) was asked about.
const journeyDiffStore = new Map<string, unknown>();

// --- Human Review / Exception Resolution mock state ---
type MockRole = 'CUSTOMER' | 'REVIEW_OFFICER';
let mockRole: MockRole = 'CUSTOMER';

interface MockReviewCase {
  case_id: string;
  case_number: string;
  journey_id: string;
  journey_type: string;
  journey_display_name: string;
  field_key: string;
  reason_code: string;
  reason_title: string;
  reason_description: string;
  priority: string;
  status: string;
  case_version: number;
  assigned_reviewer: string | null;
  is_locked: boolean;
  resolution_type: string | null;
  resolution_reason: string | null;
  resolution_notes: string | null;
  requested_information: { requested_docs: string[]; customer_message: string } | null;
  escalation_reason: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  journey_context?: unknown;
  evidence?: unknown[];
}

const reviewCaseStore = new Map<string, MockReviewCase>();

function seedReviewCaseStore(): void {
  reviewCaseStore.clear();
  const demo = deepClone(reviewCaseDemoFixture) as MockReviewCase & {
    evidence: unknown[];
  };
  reviewCaseStore.set(demo.case_id, {
    ...demo,
    journey_context: journeyStore.get(demo.journey_id) ?? lendingV1State,
  });
  mockRole = 'CUSTOMER';
}

function forbidden() {
  return HttpResponse.json(
    { error: { code: 'FORBIDDEN', message: 'This action requires Review Center access.' } },
    { status: 403 }
  );
}

function notFound(message: string) {
  return HttpResponse.json({ error: { code: 'NOT_FOUND', message } }, { status: 404 });
}

function staleCase() {
  return HttpResponse.json(
    {
      error: {
        code: 'REVIEW_CASE_STALE',
        message: 'This case changed while you were reviewing it. Refresh before submitting.',
      },
    },
    { status: 409 }
  );
}

function withoutDetail(c: MockReviewCase): Omit<MockReviewCase, 'journey_context' | 'evidence'> {
  const { journey_context: _jc, evidence: _ev, ...rest } = c;
  return rest;
}

function seedJourneyStore(): void {
  journeyStore.clear();
  journeyDiffStore.clear();
  for (const type of Object.keys(packInitialStates)) {
    if (type === 'LENDING') continue; // Lending uses the step-based fixtures directly.
    const initial = deepClone(packInitialStates[type]) as MockJourney;
    journeyStore.set(initial.journey_id, initial);
  }
}

// All mutable mock state above (`currentLendingStep`, `journeyStore`,
// `journeyDiffStore`) previously lived only in this module's own in-memory
// variables. That module is re-evaluated from scratch on every full page
// load - not just an explicit refresh, but any same-origin navigation this
// mock layer doesn't special-case - so a user who refreshed mid-journey (or
// even right after reaching "Application Ready!") saw every pack's progress
// silently revert to its pristine initial state, for real: confirmed by
// driving a real browser through several real actions, then observing
// `version_number` and `progress` both roll back after nothing more than a
// same-origin `page.goto()`. The real backend has no such problem (Postgres
// snapshots are genuinely durable); this was mock-layer-only. Session-scoped
// persistence is explicitly sanctioned for exactly this file (see this
// project's CLAUDE.md: "NEVER use localStorage/sessionStorage for app state
// (sessionStorage in MSW handlers only)"), and `scenarios.ts` already
// establishes the same pattern for scenario overrides.
const MOCK_STATE_STORAGE_KEY = 'pf_mock_journey_state_v1';

function persistMockState(): void {
  if (typeof window === 'undefined' || !window.sessionStorage) return;
  try {
    window.sessionStorage.setItem(
      MOCK_STATE_STORAGE_KEY,
      JSON.stringify({
        currentLendingStep,
        journeys: Array.from(journeyStore.entries()),
        diffs: Array.from(journeyDiffStore.entries()),
      })
    );
  } catch {
    // Storage full/unavailable (private browsing, quota) - fail open. The
    // demo still works for this page load, it just won't survive a refresh.
  }
}

function clearPersistedMockState(): void {
  if (typeof window === 'undefined' || !window.sessionStorage) return;
  try {
    window.sessionStorage.removeItem(MOCK_STATE_STORAGE_KEY);
  } catch {
    // ignore
  }
}

function loadMockState(): void {
  seedJourneyStore();
  if (typeof window === 'undefined' || !window.sessionStorage) return;
  try {
    const raw = window.sessionStorage.getItem(MOCK_STATE_STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as {
      currentLendingStep?: number;
      journeys?: [string, MockJourney][];
      diffs?: [string, unknown][];
    };
    if (typeof parsed.currentLendingStep === 'number') {
      currentLendingStep = parsed.currentLendingStep;
    }
    if (Array.isArray(parsed.journeys)) {
      journeyStore.clear();
      for (const [id, journey] of parsed.journeys) journeyStore.set(id, journey);
    }
    if (Array.isArray(parsed.diffs)) {
      journeyDiffStore.clear();
      for (const [id, diff] of parsed.diffs) journeyDiffStore.set(id, diff);
    }
  } catch {
    // Corrupt/incompatible stored state - fall back to the fresh seed
    // already applied above rather than crash the app.
  }
}
loadMockState();
seedReviewCaseStore();

export function resetMockState(): void {
  currentLendingStep = 1;
  seedJourneyStore();
  seedReviewCaseStore();
  clearPersistedMockState();
}

export function setLendingStep(step: number): void {
  currentLendingStep = step;
  persistMockState();
}

// A resolve_action_id naming an EVIDENCE action is, by the same convention
// Screen06 itself already relies on (`actionId.replace(/^UPLOAD_/, '')` for
// doc_type), always prefixed UPLOAD_. This is a naming-convention check, not
// a per-journey-type or per-action-id special case - it applies identically
// to every pack.
function inferActionKind(actionId: string): 'EVIDENCE' | 'FORM' {
  return actionId.startsWith('UPLOAD_') ? 'EVIDENCE' : 'FORM';
}

function buildGenericActionOption(field: MockField): Record<string, unknown> {
  const actionId = field.resolve_action_id as string;
  const kind = inferActionKind(actionId);
  return {
    action_id: actionId,
    title: field.label,
    kind,
    why: field.explanation || `Resolve ${field.label} to continue.`,
    unlocks: [field.key],
    accepts: kind === 'EVIDENCE' ? [actionId.replace(/^UPLOAD_/, '')] : null,
    input_schema:
      kind === 'FORM'
        ? [{ key: field.key, type: 'text', label: field.label, required: true }]
        : null,
  };
}

function buildGenericRecommendation(journey: MockJourney): Record<string, unknown> {
  const blocked = journey.fields.filter((f) => f.status === 'BLOCKED' && f.resolve_action_id);
  const ambiguous = journey.fields.find((f) => f.status === 'AMBIGUOUS');

  // Dedupe by action_id (two fields can share one resolve_action_id) - needed
  // by both branches below.
  const seen = new Set<string>();
  const options = blocked.filter((f) => {
    if (seen.has(f.resolve_action_id as string)) return false;
    seen.add(f.resolve_action_id as string);
    return true;
  });

  if (ambiguous) {
    // The clarification is the PRIMARY recommendation, but every other
    // already-blocked field must remain independently resolvable - it still
    // has its own Resolve button on Screen 4, and that button navigates
    // straight to /act/<its resolve_action_id>. Screen06 (the action screen)
    // resolves its title/why/input_schema by matching `recommendation` OR
    // `alternatives` against the actionId in the URL; leaving `alternatives`
    // empty here (as this used to) meant that match always failed whenever a
    // journey had a pending clarification, so those fields' action screens
    // silently fell back to a generic placeholder title instead of their
    // real one (Screen06 itself now shows a safe "not available" state,
    // never invented fields, whenever `action` can't be resolved at all).
    return {
      snapshot_id: journey.snapshot_id,
      readiness: 'NEEDS_REVIEW',
      recommendation: {
        action_id: `CLARIFY_${ambiguous.key.toUpperCase()}`,
        title: 'Provide Clarification',
        kind: 'CLARIFICATION',
        why: ambiguous.explanation || 'Clarification required to unblock this journey.',
        unlocks: [ambiguous.key],
        accepts: null,
        input_schema: null,
      },
      alternatives: options.map(buildGenericActionOption),
      minimum_path_length: 1 + options.length,
      source: 'PLANNER_FALLBACK',
    };
  }

  if (blocked.length === 0) {
    return {
      snapshot_id: journey.snapshot_id,
      readiness: journey.readiness,
      recommendation: null,
      alternatives: [],
      minimum_path_length: 0,
      source: 'AI_RANKED',
    };
  }

  return {
    snapshot_id: journey.snapshot_id,
    readiness: journey.readiness,
    recommendation: buildGenericActionOption(options[0]),
    alternatives: options.slice(1).map(buildGenericActionOption),
    minimum_path_length: options.length,
    source: 'AI_RANKED',
  };
}

// Applies a FORM/EVIDENCE action generically: satisfies every field whose
// resolve_action_id matches, using the caller's own submitted values where
// given (never inventing a number), recomputes progress/readiness, and
// returns the same {journey, diff, next_recommendation} shape the real
// mutation endpoint returns.
function applyGenericAction(
  journey: MockJourney,
  actionId: string,
  input: Record<string, unknown> | undefined
): { journey: MockJourney; diff: Record<string, unknown> } {
  const fromVersion = journey.version_number;
  const fieldsChanged: Record<string, unknown>[] = [];
  const matched = journey.fields.filter((f) => f.resolve_action_id === actionId);

  for (const field of matched) {
    if (field.status === 'SATISFIED') continue;
    const submitted = input && field.key in input ? input[field.key] : undefined;
    const fromStatus = field.status;
    field.status = 'SATISFIED';
    field.value = submitted !== undefined ? submitted : true;
    field.display_value = submitted !== undefined ? String(submitted) : 'Verified';
    field.resolve_action_id = null;

    // completed += 1; prefer clearing a "blocker" (the field this action was
    // the recommended fix for) before an ordinary "pending" count, so the
    // three counters stay internally consistent (completed+pending+blockers
    // === total) without needing to model the real backend's full blocker-vs
    // -pending planner semantics in this mock layer.
    journey.progress.completed += 1;
    if (journey.progress.blockers > 0) journey.progress.blockers -= 1;
    else if (journey.progress.pending > 0) journey.progress.pending -= 1;

    fieldsChanged.push({
      key: field.key,
      label: field.label,
      from_status: fromStatus,
      to_status: 'SATISFIED',
      display_value: field.display_value,
      cause: `ACTION:${actionId}`,
      cascaded: false,
    });
  }

  const progressBefore = deepClone(journey.progress);
  progressBefore.completed -= fieldsChanged.length;
  if (journey.progress.blockers < progressBefore.blockers) progressBefore.blockers += fieldsChanged.length;
  else progressBefore.pending += fieldsChanged.length;

  journey.version_number += 1;
  journey.snapshot_id = randomId('snap');
  const readinessFrom = journey.readiness;
  journey.readiness =
    journey.progress.pending === 0 && journey.progress.blockers === 0 ? 'READY' : 'NOT_READY';
  if (journey.readiness === 'READY') journey.status = 'COMPLETED';

  const diff = {
    from_version: fromVersion,
    to_version: journey.version_number,
    fields_changed: fieldsChanged,
    actions_unlocked: [],
    actions_removed: matched.length > 0 ? [actionId] : [],
    readiness: { from: readinessFrom, to: journey.readiness },
    progress: { from: progressBefore, to: deepClone(journey.progress) },
  };

  journey.updated_at = new Date().toISOString();
  journeyStore.set(journey.journey_id, journey);
  journeyDiffStore.set(journey.journey_id, diff);
  persistMockState();

  return { journey, diff };
}

// Minimal manual multipart/form-data parser for text fields (doc_type,
// manual_fields) and the uploaded file's name. Used instead of
// `Request.formData()` because jsdom's fetch/FormData polyfill (the test
// environment this mock layer runs under) does not reliably round-trip a
// multipart body through MSW's node interceptor - `request.formData()` throws
// "Content-Type was not one of multipart/form-data..." there even though the
// same request works correctly in a real browser. Parsing the raw body text
// against the boundary is environment-agnostic and needs nothing beyond the
// Fetch API's own Request/Headers.
async function parseMultipartFields(
  request: Request
): Promise<{ fields: Record<string, string>; filename: string | null }> {
  try {
    const contentType = request.headers.get('content-type') || '';
    const boundaryMatch = contentType.match(/boundary=(?:"([^"]+)"|([^;]+))/);
    const boundary = boundaryMatch ? boundaryMatch[1] || boundaryMatch[2] : null;

    let body = '';
    try {
      body = await request.clone().text();
    } catch {
      try {
        body = await request.text();
      } catch {
        return { fields: {}, filename: null };
      }
    }

    if (!boundary || !body) {
      return { fields: {}, filename: null };
    }

    const parts = body.split(`--${boundary}`);
    const fields: Record<string, string> = {};
    let filename: string | null = null;

    for (const part of parts) {
      const nameMatch = part.match(/name="([^"]+)"/);
      if (!nameMatch) continue;

      const filenameMatch = part.match(/filename="([^"]*)"/);
      if (filenameMatch) {
        filename = filenameMatch[1] || null;
        continue;
      }

      const valueSection = part.split(/\r?\n\r?\n/)[1];
      if (valueSection !== undefined) {
        fields[nameMatch[1]] = valueSection.replace(/\r?\n--\s*$/, '').trim();
      }
    }

    return { fields, filename };
  } catch {
    return { fields: {}, filename: null };
  }
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

    const list = journeysListFixture.journeys.map((item) => {
      const stored = journeyStore.get(item.journey_id);
      if (stored) {
        return {
          ...item,
          status: stored.status,
          readiness: stored.readiness,
          progress: stored.progress,
          updated_at: (stored.updated_at as string) || item.updated_at,
          resume_screen:
            stored.readiness === 'READY'
              ? 'COMPLETE'
              : stored.readiness === 'NEEDS_REVIEW'
              ? 'NEEDS_REVIEW'
              : 'STATUS',
        };
      }
      return item;
    });

    return HttpResponse.json({ journeys: list });
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

    const initialState = deepClone(packInitialStates[type] || lendingV1State) as MockJourney;
    initialState.updated_at = new Date().toISOString();
    if (type === 'LENDING') {
      currentLendingStep = 1;
    }
    // Fresh creation always resets that pack's demo journey back to its
    // pristine initial state, even if a previous action in this session
    // had already mutated it.
    journeyStore.set(initialState.journey_id, initialState);
    journeyDiffStore.delete(initialState.journey_id);
    persistMockState();

    return HttpResponse.json(initialState, { status: 201 });
  }),

  // 7. GET /api/v1/journeys/:journey_id (Screen 4)
  http.get('*/api/v1/journeys/:journey_id', async ({ request, params }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    if (scenario === 'deadend') {
      return HttpResponse.json(lendingErrorDeadend);
    }

    const journeyId = String(params.journey_id);
    if (journeyId !== LENDING_JOURNEY_ID) {
      const stored = journeyStore.get(journeyId);
      if (!stored) {
        return HttpResponse.json(
          { error: { code: 'NOT_FOUND', message: 'Journey not found or unavailable' } },
          { status: 404 }
        );
      }
      return HttpResponse.json(stored);
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
  http.get('*/api/v1/journeys/:journey_id/recommendation', async ({ request, params }) => {
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

    const journeyId = String(params.journey_id);
    if (journeyId !== LENDING_JOURNEY_ID) {
      const stored = journeyStore.get(journeyId);
      if (!stored) {
        return HttpResponse.json(
          { error: { code: 'NOT_FOUND', message: 'Journey not found or unavailable' } },
          { status: 404 }
        );
      }
      return HttpResponse.json(buildGenericRecommendation(stored));
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
  //
  // Root cause of the "analysis screen reuses the previous document" bug: this
  // handler used to unconditionally return the salary-slip fixture, regardless of
  // which action/document the request was actually for. `doc_type` (a real,
  // required field on this contract's request body - "Allowed doc_type values for
  // EVIDENCE actions") is the one piece of the request that tells us which
  // document this upload actually is, so every branch below keys off it. There is
  // no per-journey-type or per-action_id special-casing here - only per-doc_type,
  // which is exactly what the contract says this field is for.
  http.post('*/api/v1/journeys/:journey_id/evidence', async ({ request, params }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    const journeyId = String(params.journey_id);

    if (scenario === 'needsreview' && journeyId === LENDING_JOURNEY_ID) {
      return HttpResponse.json(lendingEvidenceBankStatement);
    }

    let docType = '';
    let uploadedFilename: string | null = null;
    let parsedFields: Record<string, string> = {};
    try {
      const parsed = await parseMultipartFields(request);
      parsedFields = parsed.fields;
      docType = (parsed.fields.doc_type || '').toUpperCase();
      uploadedFilename = parsed.filename;
    } catch {
      docType = 'SALARY_SLIP';
    }
    if (!docType) {
      docType = 'SALARY_SLIP';
    }

    if (journeyId !== LENDING_JOURNEY_ID) {
      // Generic evidence preview for non-flagship journeys: find the field
      // this doc_type's action would satisfy (by the same UPLOAD_<doc_type>
      // naming convention used everywhere else in this mock), and preview
      // satisfying THAT field - never another journey's or another
      // document's data.
      const stored = journeyStore.get(journeyId);
      const targetField = stored?.fields.find(
        (f) => f.resolve_action_id === `UPLOAD_${docType}`
      );
      const filename = uploadedFilename || `${docType.toLowerCase() || 'document'}.pdf`;
      const detected = targetField
        ? [{ key: targetField.key, label: targetField.label, display_value: 'Verified' }]
        : [];

      return HttpResponse.json({
        evidence_id: randomId(`ev-${docType.toLowerCase() || 'doc'}`),
        filename,
        uploaded_at: new Date().toISOString(),
        size_bytes: 0,
        interpretation: {
          verified: detected.length > 0,
          confidence: detected.length > 0 ? 0.9 : 0,
          detected,
          summary: targetField
            ? `Verified ${targetField.label.toLowerCase()} from the submitted ${docType.toLowerCase() || 'document'}.`
            : `Received ${docType || 'document'}. No matching requirement found for this journey.`,
          conflicts: [],
        },
        proposed_action_id: targetField ? `UPLOAD_${docType}` : null,
        consequence_preview: null,
        diff_preview: null,
        requires_review: false,
      });
    }

    const fixtureByDocType: Record<string, unknown> = {
      SALARY_SLIP: lendingEvidenceSalarySlip,
      BANK_STATEMENT: lendingEvidenceBankStatementVerified,
      ADDRESS_PROOF: lendingEvidenceAddressProof,
    };

    const curated = fixtureByDocType[docType];
    if (curated) {
      return HttpResponse.json(curated);
    }

    // No curated fixture for this doc_type - rather than silently falling back to
    // salary-slip data (the exact bug being fixed here), synthesize a response
    // that is honestly derived from the request itself: it names the real
    // doc_type, echoes back only the values the caller actually submitted (via
    // manual_fields) with no invented numbers, and is clearly a generic/unverified
    // result rather than a fabricated specific one.
    let manualFields: Record<string, unknown> = {};
    if (parsedFields.manual_fields) {
      try {
        manualFields = JSON.parse(parsedFields.manual_fields) as Record<string, unknown>;
      } catch {
        manualFields = {};
      }
    }
    const filename = uploadedFilename || `${docType.toLowerCase() || 'document'}.pdf`;
    const detected = Object.entries(manualFields).map(([key, value]) => ({
      key,
      label: key.replace(/_/g, ' '),
      display_value: String(value),
    }));

    return HttpResponse.json({
      evidence_id: `generic-${docType.toLowerCase() || 'unknown'}-${Date.now()}`,
      filename,
      uploaded_at: new Date().toISOString(),
      size_bytes: 0,
      interpretation: {
        verified: detected.length > 0,
        confidence: detected.length > 0 ? 0.75 : 0,
        detected,
        summary:
          detected.length > 0
            ? `Received ${docType || 'document'} and recorded the submitted values.`
            : `Received ${docType || 'document'}. No structured fields could be confirmed from this submission.`,
        conflicts: [],
      },
      proposed_action_id: null,
      consequence_preview: null,
      diff_preview: null,
      requires_review: false,
    });
  }),

  // 10. POST /api/v1/journeys/:journey_id/actions (Action Mutation)
  http.post('*/api/v1/journeys/:journey_id/actions', async ({ request, params }) => {
    const scenario = getActiveScenario(request.url, request);
    if (scenario === 'slow') await delay(1000);

    if (scenario === 'stale') {
      return HttpResponse.json(lendingErrorStale, { status: 409 });
    }

    if (scenario === 'invalid') {
      return HttpResponse.json(lendingErrorInvalid, { status: 422 });
    }

    const journeyId = String(params.journey_id);
    if (journeyId !== LENDING_JOURNEY_ID) {
      const stored = journeyStore.get(journeyId);
      if (!stored) {
        return HttpResponse.json(
          { error: { code: 'NOT_FOUND', message: 'Journey not found or unavailable' } },
          { status: 404 }
        );
      }
      const body = (await request.json()) as {
        action_id?: string;
        expected_snapshot_id?: string;
        input?: Record<string, unknown>;
      };
      if (body.expected_snapshot_id && body.expected_snapshot_id !== stored.snapshot_id) {
        return HttpResponse.json(
          {
            error: {
              code: 'ACTION_STALE',
              message: 'The journey state has changed since this action was requested',
              details: { current_snapshot_id: stored.snapshot_id },
            },
          },
          { status: 409 }
        );
      }
      const { journey, diff } = applyGenericAction(stored, body.action_id || '', body.input);
      return HttpResponse.json({
        journey,
        diff,
        next_recommendation: buildGenericRecommendation(journey),
      });
    }

    // Advance step in sequence
    if (currentLendingStep === 1) {
      currentLendingStep = 2;
      persistMockState();
      return HttpResponse.json(lendingV2Action);
    }

    if (currentLendingStep === 2 || currentLendingStep === 3) {
      currentLendingStep = 4;
      persistMockState();
      return HttpResponse.json(lendingV4Clarification);
    }

    currentLendingStep = 5;
    persistMockState();
    return HttpResponse.json({
      journey: lendingV5Ready,
      diff: lendingV4Clarification.diff,
      next_recommendation: null,
    });
  }),

  // 11. POST /api/v1/journeys/:journey_id/clarifications (Needs Review Resolution)
  http.post('*/api/v1/journeys/:journey_id/clarifications', async ({ request, params }) => {
    const scenario = getActiveScenario(request.url, request);
    if (scenario === 'slow') await delay(1000);

    if (scenario === 'stale') {
      return HttpResponse.json(lendingErrorStale, { status: 409 });
    }

    const journeyId = String(params.journey_id);
    if (journeyId !== LENDING_JOURNEY_ID) {
      const stored = journeyStore.get(journeyId);
      if (!stored) {
        return HttpResponse.json(
          { error: { code: 'NOT_FOUND', message: 'Journey not found or unavailable' } },
          { status: 404 }
        );
      }
      const body = (await request.json()) as {
        field?: string;
        answer?: unknown;
        expected_snapshot_id?: string;
      };
      if (body.expected_snapshot_id && body.expected_snapshot_id !== stored.snapshot_id) {
        return HttpResponse.json(
          {
            error: {
              code: 'ACTION_STALE',
              message: 'The journey state has changed since this action was requested',
              details: { current_snapshot_id: stored.snapshot_id },
            },
          },
          { status: 409 }
        );
      }
      const field = stored.fields.find((f) => f.key === body.field);
      const fromVersion = stored.version_number;
      if (field && field.status === 'AMBIGUOUS') {
        field.status = 'SATISFIED';
        field.value = body.answer;
        field.display_value = String(body.answer);
        delete field.ambiguity;
        stored.progress.completed += 1;
        if (stored.progress.pending > 0) stored.progress.pending -= 1;
        else if (stored.progress.blockers > 0) stored.progress.blockers -= 1;
        stored.version_number += 1;
        stored.snapshot_id = randomId('snap');
        stored.readiness =
          stored.progress.pending === 0 && stored.progress.blockers === 0 ? 'READY' : 'NOT_READY';
        stored.status = stored.readiness === 'READY' ? 'COMPLETED' : 'IN_PROGRESS';
      }
      const diff = {
        from_version: fromVersion,
        to_version: stored.version_number,
        fields_changed: field
          ? [
              {
                key: field.key,
                label: field.label,
                from_status: 'AMBIGUOUS',
                to_status: 'SATISFIED',
                display_value: field.display_value,
                cause: `CLARIFICATION:${body.field}`,
                cascaded: false,
              },
            ]
          : [],
        actions_unlocked: [],
        actions_removed: [],
        readiness: { from: 'NEEDS_REVIEW', to: stored.readiness },
        progress: { from: stored.progress, to: stored.progress },
      };
      journeyStore.set(journeyId, stored);
      journeyDiffStore.set(journeyId, diff);
      persistMockState();
      return HttpResponse.json({
        journey: stored,
        diff,
        next_recommendation: buildGenericRecommendation(stored),
      });
    }

    currentLendingStep = 4;
    persistMockState();
    return HttpResponse.json(lendingV4Clarification);
  }),

  // 12. GET /api/v1/journeys/:journey_id/diff
  http.get('*/api/v1/journeys/:journey_id/diff', async ({ request, params }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    const journeyId = String(params.journey_id);
    if (journeyId !== LENDING_JOURNEY_ID) {
      const diff = journeyDiffStore.get(journeyId);
      if (!diff) {
        return HttpResponse.json(
          { error: { code: 'NOT_FOUND', message: 'No diff available for this journey yet' } },
          { status: 404 }
        );
      }
      return HttpResponse.json(diff);
    }

    return HttpResponse.json(lendingV2Action.diff);
  }),

  // 13. POST /api/v1/demo/reset
  http.post('*/api/v1/demo/reset', async () => {
    // Previously only reset currentLendingStep, silently leaving every
    // other pack's mutated journeyStore entries (and any persisted
    // sessionStorage state) untouched - "reset the demo" is meant to give a
    // genuinely clean slate for every pack, not just Lending.
    resetMockState();
    return HttpResponse.json({ reset: true, elapsed_ms: 12 });
  }),

  // 14. POST /api/v1/journeys/:journey_id/chat
  http.post('*/api/v1/journeys/:journey_id/chat', async ({ request }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    const body = (await request.json()) as { message?: string };
    return HttpResponse.json({
      reply: `(Mock mode) I received: "${body?.message ?? ''}". Switch to live mode for answers grounded in your real journey status.`,
    });
  }),

  // 14b. POST /api/v1/journeys/:journey_id/chat/voice (Sarvam speech-to-text)
  http.post('*/api/v1/journeys/:journey_id/chat/voice', async () => {
    return HttpResponse.json({
      transcript: '(Mock transcript) What do I need to do next?',
      language_code: 'en-IN',
      reply:
        '(Mock mode) I heard your question. Switch to live mode for answers grounded in your real journey status.',
    });
  }),

  // 15. POST /api/v1/chat (no journey context)
  http.post('*/api/v1/chat', async ({ request }) => {
    const scenario = getActiveScenario(request.url);
    if (scenario === 'slow') await delay(1000);

    const body = (await request.json()) as { message?: string };
    return HttpResponse.json({
      reply: `(Mock mode) I received: "${body?.message ?? ''}". Switch to live mode for a real assistant reply.`,
    });
  }),

  // 15b. POST /api/v1/translate (Sarvam Mayura)
  http.post('*/api/v1/translate', async ({ request }) => {
    const body = (await request.json()) as { text?: string; target_language_code?: string };
    return HttpResponse.json({
      translated_text: `[${body?.target_language_code ?? 'xx'}] ${body?.text ?? ''}`,
    });
  }),

  // --- Human Review / Exception Resolution (mock-mode) ---

  http.post('*/api/v1/review/role', async ({ request }) => {
    const body = (await request.json()) as { role?: string };
    mockRole = body?.role === 'REVIEW_OFFICER' ? 'REVIEW_OFFICER' : 'CUSTOMER';
    return HttpResponse.json({ role: mockRole });
  }),

  http.get('*/api/v1/review/dashboard', () => {
    if (mockRole !== 'REVIEW_OFFICER') return forbidden();
    const cases = Array.from(reviewCaseStore.values());
    return HttpResponse.json({
      pending_review: cases.filter((c) => c.status === 'REVIEW_REQUIRED').length,
      under_review: cases.filter((c) => c.status === 'UNDER_REVIEW').length,
      waiting_customer: cases.filter((c) => c.status === 'ADDITIONAL_INFO_REQUIRED').length,
      escalated: cases.filter((c) => c.status === 'ESCALATED').length,
      resolved_today: cases.filter((c) => c.status === 'RESOLVED').length,
    });
  }),

  http.get('*/api/v1/review/cases', ({ request }) => {
    if (mockRole !== 'REVIEW_OFFICER') return forbidden();
    const url = new URL(request.url);
    const status = url.searchParams.get('status');
    let cases = Array.from(reviewCaseStore.values());
    if (status) cases = cases.filter((c) => c.status === status);
    return HttpResponse.json({
      cases: cases.map(({ journey_context: _jc, evidence: _ev, ...rest }) => rest),
    });
  }),

  http.get('*/api/v1/review/cases/:case_id', ({ params }) => {
    if (mockRole !== 'REVIEW_OFFICER') return forbidden();
    const c = reviewCaseStore.get(String(params.case_id));
    if (!c) return notFound('Review case not found');
    return HttpResponse.json(c);
  }),

  http.get('*/api/v1/review/cases/:case_id/audit', ({ params }) => {
    if (mockRole !== 'REVIEW_OFFICER') return forbidden();
    const c = reviewCaseStore.get(String(params.case_id));
    if (!c) return notFound('Review case not found');
    return HttpResponse.json({
      entries: [
        { event_type: 'REVIEW_CASE_CREATED', payload: {}, created_at: c.created_at },
      ],
    });
  }),

  http.post('*/api/v1/review/cases/:case_id/ai-summary', ({ params }) => {
    if (mockRole !== 'REVIEW_OFFICER') return forbidden();
    const c = reviewCaseStore.get(String(params.case_id));
    if (!c) return notFound('Review case not found');
    return HttpResponse.json({
      summary:
        'Mock AI summary: the customer declared one value for this field, submitted evidence ' +
        'indicates a different value, and the case is currently pending reviewer resolution.',
      disclaimer:
        'AI-generated summary. Review system evidence and deterministic assessment before taking action.',
    });
  }),

  http.post('*/api/v1/review/cases/:case_id/claim', async ({ params, request }) => {
    if (mockRole !== 'REVIEW_OFFICER') return forbidden();
    const c = reviewCaseStore.get(String(params.case_id));
    if (!c) return notFound('Review case not found');
    const body = (await request.json()) as { expected_case_version?: number };
    if (body.expected_case_version !== c.case_version) return staleCase();
    c.status = 'UNDER_REVIEW';
    c.assigned_reviewer = 'Reviewer-mock';
    c.is_locked = true;
    c.case_version += 1;
    c.updated_at = new Date().toISOString();
    return HttpResponse.json(withoutDetail(c));
  }),

  http.post('*/api/v1/review/cases/:case_id/request-information', async ({ params, request }) => {
    if (mockRole !== 'REVIEW_OFFICER') return forbidden();
    const c = reviewCaseStore.get(String(params.case_id));
    if (!c) return notFound('Review case not found');
    const body = (await request.json()) as {
      expected_case_version?: number;
      requested_docs?: string[];
      customer_message?: string;
    };
    if (body.expected_case_version !== c.case_version) return staleCase();
    c.status = 'ADDITIONAL_INFO_REQUIRED';
    c.requested_information = {
      requested_docs: body.requested_docs ?? [],
      customer_message: body.customer_message ?? '',
    };
    c.case_version += 1;
    c.updated_at = new Date().toISOString();
    return HttpResponse.json(withoutDetail(c));
  }),

  http.post('*/api/v1/review/cases/:case_id/escalate', async ({ params, request }) => {
    if (mockRole !== 'REVIEW_OFFICER') return forbidden();
    const c = reviewCaseStore.get(String(params.case_id));
    if (!c) return notFound('Review case not found');
    const body = (await request.json()) as {
      expected_case_version?: number;
      escalation_reason?: string;
    };
    if (body.expected_case_version !== c.case_version) return staleCase();
    c.status = 'ESCALATED';
    c.escalation_reason = body.escalation_reason ?? '';
    c.case_version += 1;
    c.updated_at = new Date().toISOString();
    return HttpResponse.json(withoutDetail(c));
  }),

  http.post('*/api/v1/review/cases/:case_id/resolve', async ({ params, request }) => {
    if (mockRole !== 'REVIEW_OFFICER') return forbidden();
    const c = reviewCaseStore.get(String(params.case_id));
    if (!c) return notFound('Review case not found');
    const body = (await request.json()) as {
      expected_case_version?: number;
      resolution_type?: string;
      resolution_reason?: string;
      resolution_notes?: string;
    };
    if (body.expected_case_version !== c.case_version) return staleCase();
    if (!body.resolution_reason?.trim()) {
      return HttpResponse.json(
        { error: { code: 'VALIDATION_ERROR', message: 'resolution_reason is required' } },
        { status: 400 }
      );
    }
    c.status = 'RESOLVED';
    c.resolution_type = body.resolution_type ?? null;
    c.resolution_reason = body.resolution_reason;
    c.resolution_notes = body.resolution_notes ?? null;
    c.resolved_at = new Date().toISOString();
    c.case_version += 1;
    c.updated_at = new Date().toISOString();
    return HttpResponse.json(c);
  }),

  http.get('*/api/v1/journeys/:journey_id/review-status', ({ params }) => {
    const journeyId = String(params.journey_id);
    const openCase = Array.from(reviewCaseStore.values()).find(
      (c) => c.journey_id === journeyId && !['RESOLVED', 'CANCELLED'].includes(c.status)
    );
    if (!openCase) {
      return HttpResponse.json({ has_open_case: false });
    }
    return HttpResponse.json({
      has_open_case: true,
      case_number: openCase.case_number,
      status: openCase.status,
      title: 'Additional verification required',
      description:
        'We found information that needs a quick manual review before you can continue.',
      requested_information: openCase.requested_information,
      updated_at: openCase.updated_at,
    });
  }),
];
