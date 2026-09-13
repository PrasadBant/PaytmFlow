# Dev 1 — Frontend / Product — Implementation Plan

**You own:** every pixel the user sees, all client state, API integration, error and loading behaviour, responsiveness, accessibility, and frontend testing.

**You do not own:** any business logic. Zero. If you find yourself computing whether a field is blocked, deciding what the next action should be, or formatting a currency value, stop — that belongs to Dev2 and the contract already supplies it.

**Your independence guarantee:** from T+3 to T+26 you never need Dev2. You build against MSW handlers driven by `contract/fixtures/`. Your Playwright suite goes green before the backend exists.

---

## 1. Responsibilities and features

| # | Feature | Source |
|---|---|---|
| 1 | Screens 1–10 exactly as the reference PNG | UI/UX Spec §3–12 |
| 2 | AppShell: sidebar (Home / Start Journey / My Journeys / Help), header, notification icon, avatar | App Flow §1 |
| 3 | Six-journey selection with the Lending "Flagship Demo" badge | FRD §4 |
| 4 | **Schema-driven goal form** — rendered from `goal_schema`, works for all six packs unmodified | FRD §5 |
| 5 | Optional natural-language input behind progressive disclosure, never replacing the form | Canonical §4 |
| 6 | Progress ring `3/7 Completed` — progress only, never a score | Canonical §4, FRD §6 |
| 7 | Blocker cards with explanation + `Resolve →` | FRD §6 |
| 8 | Recommendation card + valid alternatives + `Need help?` panel | FRD §7 |
| 9 | Evidence upload: dropzone, Enter Details tab, How it helps tab, 10MB cap | FRD §8 |
| 10 | AI Analysis screen — Expected Outcome rendered from `consequence_preview`, never from AI text | FRD §9 |
| 11 | `<JourneyDiff/>` as one reusable component, used on Screens 7 and 8 | Canonical §4 |
| 12 | Updated Status with celebratory visual | FRD §10 |
| 13 | Complete Journey — handoff wording, never approval | FRD §11 |
| 14 | My Journeys with All / In Progress / Completed / Needs Review tabs and resume | FRD §12 |
| 15 | Needs Review — exactly one question at a time | FRD §13 |
| 16 | **Generic FORM action modal** rendered from `input_schema` — this is how non-evidence actions work across all packs | contract `ActionOption.kind` |
| 17 | Stale / invalid / dead-end / network error handling | App Flow §14–15 |
| 18 | Loading, error and empty states everywhere | Build Prompt QA §4 |
| 19 | Responsive: desktop → tablet → mobile drawer | UI/UX §14 |
| 20 | Accessibility: keyboard, focus, semantics, status not by colour alone | FRD §14 |

**Explicitly not yours:** approval logic (doesn't exist), analytics dashboards (banned), chatbot UI (banned), dark mode (banned), any percentage or gauge (banned).

---

## 2. Tech stack

| Concern | Choice | Why this one |
|---|---|---|
| Framework | React 18 + TypeScript 5 (strict) | Canonical Tech Spec §1 |
| Build | Vite 5 | Canonical |
| Styling | Tailwind CSS 3 + CSS variables for tokens | Canonical |
| Routing | React Router 6 | Screens map to routes; resume needs deep links |
| Server state | TanStack Query 5 | Caching + invalidation is exactly the "recompute" model |
| UI state | Zustand | ~40 lines for sidebar/tabs. Redux would be overkill |
| Forms | React Hook Form + Zod | Schema-driven rendering needs runtime validation from `goal_schema` |
| Types | `openapi-typescript` | Generated from the contract, never hand-written |
| Mocking | MSW 2 | Same handlers serve dev, Vitest and Playwright |
| Icons | lucide-react | Matches the reference's line-icon style |
| Unit tests | Vitest + Testing Library | Canonical |
| E2E | Playwright | Canonical |
| Lint | ESLint + Prettier + `eslint-plugin-jsx-a11y` | a11y is a P0 requirement, so lint it |

**Do not add:** a component library with its own design language (shadcn/MUI/Chakra) — the reference image is the design system and you'll spend more time overriding than building. Build ~10 primitives yourself; an agent does this in 30 minutes.

---

## 3. Folder structure

```
frontend/
├── index.html
├── vite.config.ts                    # proxy /api -> :8000
├── tailwind.config.ts
├── playwright.config.ts
├── CLAUDE.md                         # agent context — see §9
├── .env.example
└── src/
    ├── main.tsx  App.tsx
    ├── app/
    │   ├── router.tsx                # all 10 routes
    │   ├── providers.tsx             # QueryClient, MSW boot, error boundary
    │   └── boot.ts                   # GET /session before first paint
    ├── api/
    │   ├── types.gen.ts              # GENERATED — never edit
    │   ├── client.ts                 # fetch wrapper: credentials, error envelope -> ApiError
    │   ├── errors.ts                 # ApiError class + code -> UX mapping (contract §5.1)
    │   └── hooks/
    │       ├── usePacks.ts  useJourney.ts  useRecommendation.ts
    │       ├── useCreateJourney.ts  useApplyAction.ts
    │       ├── useUploadEvidence.ts  useClarification.ts  useJourneyList.ts
    ├── mocks/
    │   ├── browser.ts  server.ts
    │   ├── handlers.ts               # built from contract/fixtures
    │   └── scenarios.ts              # ?scenario=stale | deadend | needsreview
    ├── components/
    │   ├── primitives/               # Button Card Badge Input Select Tabs Modal Spinner
    │   ├── AppShell.tsx  Sidebar.tsx  Header.tsx
    │   ├── JourneyCard.tsx  StatusBadge.tsx  ProgressRing.tsx
    │   ├── BlockerCard.tsx  RecommendationCard.tsx  ActionList.tsx
    │   ├── EvidenceDropzone.tsx  EvidenceCard.tsx
    │   ├── ConsequencePreview.tsx  JourneyDiff.tsx
    │   ├── SuccessState.tsx  JourneyHistoryList.tsx  AssistantHelpCard.tsx
    │   ├── NeedsReviewCard.tsx  DeadEndState.tsx
    │   ├── LoadingState.tsx  ErrorState.tsx  EmptyState.tsx  StaleBanner.tsx
    │   └── SchemaForm/               # THE key component — see §5
    │       ├── SchemaForm.tsx  FieldRenderer.tsx  toZodSchema.ts
    ├── screens/
    │   ├── Screen01Home.tsx ... Screen10MyJourneys.tsx
    ├── hooks/   state/   lib/   styles/
└── tests/
    ├── unit/                         # Vitest
    └── e2e/                          # Playwright
```

---

## 4. Route map

| Route | Screen | Data | Notes |
|---|---|---|---|
| `/` | 1 Home | — | Shows resume chip if `GET /journeys` non-empty |
| `/start` | 2 Selection | `usePacks()` | |
| `/start/:type` | 3 Goal | `usePack(type)` | Form from `goal_schema` |
| `/j/:id` | 4 Status | `useJourney(id)` | |
| `/j/:id/next` | 5 Recommendation | `useRecommendation(id)` | |
| `/j/:id/act/:actionId` | 6 Upload **or** FORM modal | from recommendation | Branch on `kind` |
| `/j/:id/analysis` | 7 AI Analysis | evidence response in route state | |
| `/j/:id/updated` | 8 Updated | action response in route state | |
| `/j/:id/complete` | 9 Complete | `useJourney(id)` | Guard: redirect unless `READY` |
| `/my-journeys` | 10 My Journeys | `useJourneyList()` | Tab = query param |

Needs Review is a component overlaid on 7 and 8, not a route.

**Resume rule:** on `/j/:id`, read `resume_screen` from the API and redirect. The server decides; you obey.

---

## 5. The two components that carry the whole product

Get these two right and the other eight screens are straightforward. Get them wrong and you'll rewrite the app twice.

### 5.1 `<SchemaForm/>` — renders any form from a field-spec array

Used by **Screen 3** (goal capture, six packs) **and** by the FORM action modal (all `kind: FORM` actions, every pack). One component, driven by `GoalFieldSpec[]` from the contract.

```tsx
type Props = {
  schema: GoalFieldSpec[];
  defaultValues?: Record<string, unknown>;
  submitLabel: string;
  onSubmit: (values: Record<string, unknown>) => void;
  isSubmitting?: boolean;
  serverErrors?: Record<string, string>;   // from VALIDATION_ERROR details
};
```

`toZodSchema(spec)` builds a Zod schema at runtime: `enum` → `z.enum` with options, `money`/`number` → `z.coerce.number().min().max()`, `text` → `z.string()`, respecting `required`. `FieldRenderer` switches on `type` to render Select / money input with ₹ prefix and Indian digit grouping / text / date / checkbox.

**This is why you never write journey-specific UI.** Insurance's goal form and Lending's goal form are the same component with different props.

### 5.2 `<JourneyDiff/>` — one component, two data sources

Screen 7 feeds it `diff_preview` (predicted). Screen 8 feeds it the real `diff`. Identical props, identical rendering. Same shape means the preview is visibly honest — which is the product's whole argument.

```tsx
type Props = { diff: JourneyDiff; variant: 'preview' | 'applied' };
```

`variant` changes only tense in the heading ("What will change" vs "What changed") and nothing else.

---

## 6. Implementation sequence

Hours are elapsed, solo, with an agent doing the typing. IDs are stable — use them in commits and in agent prompts.

### Phase F-A — Foundation (T+3 → T+8, 5h)

| ID | Task | Est | Definition of done |
|---|---|---|---|
| F00 | Vite + TS strict + Tailwind + ESLint/Prettier + a11y plugin; `vite.config.ts` proxies `/api`→8000 | 0.5h | `npm run dev` serves a blank page; `npm run lint` and `tsc --noEmit` both clean |
| F01 | `make types` → `openapi-typescript contract/openapi.yaml -o src/api/types.gen.ts`; committed | 0.25h | `JourneyStateResponse` etc. importable; file has a "GENERATED — DO NOT EDIT" header |
| F02 | `api/client.ts` (credentials include, JSON + multipart, envelope→`ApiError`), `api/errors.ts` implementing contract §5.1 | 1h | Unit test: each of the 9 error codes maps to the right UX action |
| F03 | **MSW handlers from `contract/fixtures/`** + `scenarios.ts` for `?scenario=stale\|deadend\|needsreview\|aitimeout` | 1.5h | `VITE_API_MODE=mock npm run dev` serves every endpoint; scenario switch works |
| F04 | Design tokens in `tailwind.config.ts` + `styles/tokens.css` from UI/UX §1–2 | 0.75h | Colours, radii, 8px spacing, Inter, `max-w-page`, `h-sidebar` all available as utilities |
| F05 | Primitives: Button (primary/secondary/ghost), Card, Badge, Input, MoneyInput, Select, Tabs, Modal, Spinner, IconButton | 1h | Rendered in a `/dev/kitchen-sink` route; keyboard-focusable with visible ring |

**Gate F-A:** blank app boots, mocks answer every endpoint, primitives exist.

### Phase F-B — Shell and static screens (T+8 → T+14, 6h)

| ID | Task | Est | Definition of done |
|---|---|---|---|
| F06 | `AppShell` + `Sidebar` (4 items, active state) + `Header` (wordmark, bell with dot, avatar) | 1h | Matches reference; sidebar collapses to drawer below 768px |
| F07 | Router with all 10 routes + error boundary + `boot.ts` calling `GET /session` | 0.75h | Every route renders; unknown route → 404 state |
| F08 | **Screen 1 Home** — headline, copy, CTA, hero illustration slot, 3 value cards, bottom statement | 1.25h | Copy verbatim from UI/UX §3; resume chip appears when journeys exist |
| F09 | **Screen 2 Journey Selection** — 6 cards from `usePacks()`, 2-col grid, Flagship badge on Lending | 1h | Icons map from the 6 tokens; DRAFT packs render disabled with a tooltip |
| F10 | `<SchemaForm/>` + `toZodSchema` + `FieldRenderer` (§5.1) | 1.5h | Unit tests: enum/money/required/min/max all validate; ₹ grouping correct |
| F11 | **Screen 3 Goal & Basic Info** using SchemaForm + collapsible "Describe in your own words" | 0.5h | Renders correctly for **all six** packs from fixtures without any branching |

**Gate F-B:** Screens 1→3 work end to end against mocks, for all six journeys.

### Phase F-C — The journey loop (T+14 → T+24, 10h) — *the critical path*

| ID | Task | Est | Definition of done |
|---|---|---|---|
| F12 | `<ProgressRing/>` — SVG arc, `3/7` centre, "Completed" label, `aria-label="3 of 7 steps completed"` | 0.75h | Unit test asserts **no `%` character and no word "score"** anywhere in output |
| F13 | `<BlockerCard/>` + `<StatusBadge/>` — icon + title + explanation + `Resolve →` | 0.75h | Status conveyed by icon **and** text, never colour alone |
| F14 | **Screen 4 Current Status** — ring, legend (Completed/Pending/Blockers), blocker list | 1h | Renders unmodified for all six packs; `Resolve →` routes by `resolve_action_id` |
| F15 | `<RecommendationCard/>` + `<ActionList/>` + `<AssistantHelpCard/>` | 1h | Alternatives render from `alternatives[]` only; nothing hardcoded |
| F16 | **Screen 5 Recommendation** + branch on `kind` to Screen 6 or the FORM modal | 0.75h | READY → redirect to Screen 9; DEAD_END → `<DeadEndState/>` |
| F17 | **Generic FORM action modal** — SchemaForm over `input_schema` → `POST /actions` | 1h | `SET_LOAN_TENURE` and `ADD_EMPLOYMENT_DETAILS` both work with zero bespoke code |
| F18 | `<EvidenceDropzone/>` — drag/drop, browse, type + 10MB validation, progress, cancel | 1.25h | Rejects a 12MB file and a .zip with the right message; keyboard-accessible |
| F19 | **Screen 6 Upload Evidence** — 3 tabs; Enter Details tab uses SchemaForm | 1h | "Enter Details" posts `manual_fields`; "How it helps" renders pack copy |
| F20 | `<EvidenceCard/>` + `<ConsequencePreview/>` + **Screen 7** | 1.5h | **Expected Outcome renders from `consequence_preview` only.** Add a code comment saying so |
| F21 | `<JourneyDiff/>` (§5.2) | 1h | Same component green on both a preview and an applied fixture |

**Gate F-C:** you can walk Screens 1→7 against mocks and see a deterministic preview.

### Phase F-D — Completion and history (T+24 → T+30, 6h; overlaps Integration Point 1)

| ID | Task | Est | Definition of done |
|---|---|---|---|
| F22 | **Screen 8 Updated Status** — "Progress Updated!", confetti (CSS, no library), diff, 2 CTAs | 1h | `Take Next Step` → Screen 5 with fresh data |
| F23 | **Screen 9 Complete** — success icon, checklist, `Proceed to Submit` + `Review Application` | 0.75h | Handoff modal explains no submission occurs. Test asserts "approv" never appears |
| F24 | **Screen 10 My Journeys** — 4 tabs, rows, badges, relative time, resume | 1.25h | Resume honours `resume_screen`; empty state per tab |
| F25 | `<NeedsReviewCard/>` — one question, `answer_type` → input, bounded choices | 1h | Renders exactly one question even if two ambiguities exist |
| F26 | Error surface: `<StaleBanner/>`, `<ErrorState/>`, `<EmptyState/>`, `<DeadEndState/>`, retry/backoff | 1h | All 9 error codes reachable via `?scenario=` and handled per contract §5.1 |
| F27 | Idempotency keys + double-click guards on every mutating button | 0.5h | Rapid double-click fires exactly one POST |

**Gate F-D:** full loop 1→10 against mocks, including Needs Review and every error path.

### Phase F-E — Quality (T+30 → T+40, 10h)

| ID | Task | Est | Definition of done |
|---|---|---|---|
| F28 | Responsive pass: desktop / tablet / mobile drawer | 2h | 375 / 768 / 1440 all usable; ring visible; CTA reachable |
| F29 | Accessibility pass | 1.5h | Full keyboard walk of the golden path; axe clean; `aria-live` on status |
| F30 | Vitest suite (~40 tests) | 2h | Coverage on ProgressRing maths, SchemaForm validation, JourneyDiff, error mapping |
| F31 | Playwright: Lending golden + stale + needs-review + resume, against MSW | 2h | Green in CI without a backend |
| F32 | **Prohibited-claims test** — render all 10 screens, assert the banned-word list is absent | 0.5h | Fails loudly on `approv`, `probability`, `score`, `guaranteed` |
| F33 | Visual QA against the reference PNG, screen by screen | 1.5h | Checklist in §8 signed off |
| F34 | Production build, `VITE_SHOW_DEV_BADGES=false`, deploy static bundle | 0.5h | Deployed build hits the real API through the proxy |

**Total: ~37 elapsed hours.** That is tight but real, assuming agents handle the boilerplate.

---

## 7. What you can build without Dev2 — and the mock strategy

**Everything through F33.** The only things needing a live backend: real cookie behaviour, real file upload round-trip, real latency. Those are Integration Point 1 concerns, not build concerns.

### Mock strategy

**Layer 1 — MSW from fixtures.** Handlers read `contract/fixtures/*.json`. Stateless by default: `POST /actions` returns the next fixture in the Lending sequence based on a counter in `sessionStorage`. Crude, and completely sufficient to walk the whole flow.

**Layer 2 — scenario switch.** `?scenario=` forces edge cases:

| Value | Forces |
|---|---|
| `stale` | 409 `ACTION_STALE` on the next mutation |
| `invalid` | 422 `ACTION_INVALID` |
| `needsreview` | evidence returns `requires_review: true` |
| `deadend` | journey returns `readiness: DEAD_END` |
| `aitimeout` | recommendation returns `source: PLANNER_FALLBACK`, no `why` text |
| `empty` | `GET /journeys` returns `[]` |
| `slow` | 3s delay on every response, to test loading states |

**Layer 3 — same handlers in tests.** MSW `setupServer` for Vitest, `browser.ts` for Playwright. One mock definition, three consumers, zero drift.

**When Dev2 goes live:** flip `VITE_API_MODE=live`. If your fixtures were faithful, this is a config change. That is the entire point of spending 1.5 hours on F03.

---

## 8. Testing and validation checklist

**Unit (Vitest)**
- [ ] ProgressRing: 0/7, 3/7, 7/7; no `%`; correct `aria-label`
- [ ] SchemaForm: required, min/max, enum, money coercion, ₹ grouping, server error injection
- [ ] toZodSchema: one test per `GoalFieldSpec.type`
- [ ] JourneyDiff: cascaded vs direct changes; empty diff; readiness transition
- [ ] errors.ts: all 9 codes → correct UX action
- [ ] StatusBadge: every `FieldStatus` and `JourneyStatus`
- [ ] Currency and relative-time formatting

**Component**
- [ ] BlockerCard fires `Resolve →` with the right `resolve_action_id`
- [ ] ActionList renders only `alternatives[]`
- [ ] EvidenceDropzone rejects >10MB and wrong MIME
- [ ] NeedsReviewCard renders one question given two ambiguities

**E2E (Playwright, against MSW)**
- [ ] Lending golden: 1→9, ending "Application Ready!"
- [ ] Stale: banner shows, data refetches, no duplicate mutation
- [ ] Needs Review: one question → resolved → recompute
- [ ] Resume from Screen 10 lands on the right screen
- [ ] All six packs render Screens 2→4 without error
- [ ] Keyboard-only walk of the golden path
- [ ] Mobile viewport (375px) walk of the golden path

**Visual QA vs reference PNG** — per screen: layout, spacing (8px), card radius/shadow, typography scale, CTA placement and colour, badge shapes, ring, icon style, illustration placement, empty/loading/error states.

**Claim safety** — the banned-word test (F32) must be in CI, not run manually.

---

## 9. Agentic workflow — Antigravity + Claude Code

### Division of labour between the two tools

**Antigravity** — use for work where seeing the result matters: screen layout against the reference image, responsive breakpoints, visual polish, iterating on spacing and colour. Attach the reference PNG to the conversation and work screen by screen with the browser preview open.

**Claude Code** — use for work where structure matters: scaffolding, the SchemaForm/Zod machinery, MSW handlers, the API client and error mapping, test suites, refactors across many files, and anything driven by the OpenAPI contract.

Rough split: Antigravity for F08, F09, F14, F16, F19, F22, F23, F24, F28, F33. Claude Code for F00–F05, F10, F12, F17, F20, F21, F25, F26, F30, F31, F32.

### `frontend/CLAUDE.md` — commit this at T+3, before any feature work

```markdown
# PaytmFlow Frontend — Agent Context

## What this is
Applicant-facing UI for a financial-journey recovery platform. 10 screens defined by
`docs/PaytmFlow_UI_UX_Reference_10_Screens_v4.2.png` and `docs/07_*_UI_UX_*.md`.

## Absolute rules — violating any of these is a build failure
1. NEVER render a percentage, gauge, dial, or the words score / approval / probability /
   eligibility / guaranteed. The progress ring is "3/7 Completed" and nothing else.
2. NEVER implement business logic. No computing blocked status, no deciding next actions,
   no currency formatting. The API supplies `label`, `display_value`, `explanation`,
   ordering and `resume_screen`. Render what you're given.
3. NEVER branch on journey type. No `if (journeyType === 'LENDING')`. All six journeys use
   the same components, driven by `goal_schema`, `input_schema` and `ui_labels`.
4. NEVER use dangerouslySetInnerHTML. AI-written strings reach the screen; render as text.
5. NEVER edit `src/api/types.gen.ts` — regenerate with `make types`.
6. NEVER use localStorage/sessionStorage for app state (sessionStorage in MSW handlers only).
7. Screen 7's "Expected Outcome" renders from `consequence_preview` (deterministic),
   NEVER from `interpretation.summary` (AI text). This is the core product claim.
8. Screen 9 is a handoff, never a submission. Never imply approval.

## Stack
React 18, TS strict, Vite, Tailwind (tokens in tailwind.config.ts), React Router 6,
TanStack Query 5, Zustand, React Hook Form + Zod, MSW 2, Vitest + RTL, Playwright, lucide-react.

## Conventions
- Components: PascalCase files, one component per file, named exports.
- Server state: TanStack Query only. UI state: Zustand. No prop drilling past 2 levels.
- Every mutation: send `expected_snapshot_id` + a fresh `idempotency_key` UUID.
- After a mutation, invalidate ['journey', id] and ['recommendation', id].
- Errors: throw ApiError from client.ts; map via errors.ts. Never swallow.
- Tailwind only. No inline styles, no CSS-in-JS, no new colour outside the token set.
- Every interactive element: keyboard-reachable, visible focus ring, accessible name.
- Status is never conveyed by colour alone — always icon + text.

## Definition of done for any screen
Renders from fixtures for all six packs · loading + error + empty states ·
keyboard-navigable · works at 375/768/1440 · matches the reference PNG ·
Vitest test exists · no banned words.

## Commands
npm run dev · npm run test · npm run test:e2e · npm run lint · tsc --noEmit · make types
```

### Prompts to give your agents

Keep them specific and reference the contract. Vague prompts produce plausible code that violates rules 1–8.

**F03 — MSW handlers (Claude Code)**
> Read `contract/openapi.yaml` and every file under `contract/fixtures/`. Create `src/mocks/handlers.ts` with MSW 2 handlers for all 12 endpoints, serving the fixtures. Add `src/mocks/scenarios.ts` reading a `scenario` query param supporting: `stale` (409 ACTION_STALE with `current_snapshot_id` in details), `invalid` (422), `needsreview` (evidence returns `requires_review: true`), `deadend`, `aitimeout`, `empty`, `slow` (3s delay). For `POST /journeys/{id}/actions` in the Lending flow, walk the fixture sequence v2→v3→v4→v5 using a counter in sessionStorage. Wire `browser.ts` for dev and `server.ts` for Vitest. Do not invent response fields that are not in the OpenAPI schema.

**F10 — SchemaForm (Claude Code)**
> Build `src/components/SchemaForm/`. `SchemaForm.tsx` takes `schema: GoalFieldSpec[]` (type from `src/api/types.gen.ts`), `defaultValues`, `submitLabel`, `onSubmit`, `isSubmitting`, `serverErrors`. Use React Hook Form with a Zod resolver built at runtime by `toZodSchema.ts` from the field specs: `enum`→`z.enum` from options, `money`/`number`→`z.coerce.number()` honouring min/max, `text`→`z.string()`, `date`→ISO string, `boolean`→`z.boolean()`; apply `.optional()` when `required` is false. `FieldRenderer.tsx` switches on `type` to render the right primitive from `components/primitives`. Money inputs show a ₹ prefix and Indian digit grouping (5,00,000 not 500,000) while keeping a plain number in form state. Inject `serverErrors` by key. Write Vitest tests covering every field type, required, min/max, and server error injection. This component must work for all six journey packs with no journey-specific code.

**F14 — Screen 4 (Antigravity, with the reference PNG attached)**
> Build `src/screens/Screen04CurrentStatus.tsx` to match panel 4 of the attached reference image. Data comes from `useJourney(id)` returning `JourneyStateResponse`. Layout: heading from `ui_labels.status_heading` (fallback "Your Current Status"), subtext from `ui_labels.status_subtext`; a card containing `<ProgressRing/>` on the left showing `progress.completed`/`progress.total` with "Completed" beneath, and a right-hand legend listing "{completed} Completed" (green dot), "{pending} Pending" (grey), "{blockers} Blockers" (red). Below: a "Blocked Items" heading and one `<BlockerCard/>` per field where `status !== 'SATISFIED'`, each showing `label`, `explanation` and a `Resolve →` button that routes to `/j/:id/act/:resolve_action_id`. Use only tokens from tailwind.config.ts. Never display a percentage or the word "score". Include loading and error states. Must render correctly for all six packs from fixtures — no journey-specific branching.

**F20 — Screen 7 (Claude Code)**
> Build `src/screens/Screen07AiAnalysis.tsx` from the `EvidenceResponse` passed in route state. Sections in order: `<EvidenceCard/>` (filename, relative uploaded time, a "Verified" badge when `interpretation.verified`, and each `interpretation.detected` entry as label + `display_value`); the AI summary from `interpretation.summary` rendered as a plain text node inside a tinted card; then an "Expected Outcome" list rendered ENTIRELY from `consequence_preview` — `newly_satisfied` as "{label} → Completed", `newly_unlocked` as "{title} → Unlocked", and progress as "Overall progress → {progress_after.completed}/{progress_after.total}". Then `<JourneyDiff diff={diff_preview} variant="preview" />`. Footer: Back and Continue. Continue calls `useApplyAction` with `proposed_action_id`, the current `expected_snapshot_id`, `{ evidence_id }` as input, and a fresh idempotency key, then routes to `/j/:id/updated`. If `requires_review` is true, render `<NeedsReviewCard/>` instead of Continue. CRITICAL: never derive any Expected Outcome item from `interpretation.summary` — that field is AI-generated text and consequences must come only from the deterministic `consequence_preview`. Add a code comment stating this.

**F32 — Claim safety test (Claude Code)**
> Write `tests/e2e/claim-safety.spec.ts`. Walk all 10 screens against MSW fixtures (including the READY and NEEDS_REVIEW states), capture `document.body.innerText` on each, and assert none matches `/approv|probabilit|credit score|eligibility score|readiness score|guarantee/i`. Also assert no element's text matches `/\d+\s*%/` on Screens 4, 7 or 8. Give a failure message naming the screen and the offending string. Add it to the CI job.

### Working rules with agents

1. **Give the agent the contract, not a description of it.** Point at `contract/openapi.yaml` and `types.gen.ts`. It will produce accurate code from a schema and plausible-but-wrong code from prose.
2. **One screen or one component per session.** Long sessions drift and start inventing.
3. **Make it read the reference image for anything visual.** Attach the PNG in Antigravity.
4. **Ask for the test in the same prompt.** Retrofitted tests test what the code does, not what it should do.
5. **Review for the eight rules specifically.** Agents love to add a percentage to a progress ring — that is the single most likely violation in this codebase, and it's the one that breaks the product claim.

---

## 10. Definition of done — per module

| Module | Done when |
|---|---|
| API client | All 9 error codes mapped and unit-tested; credentials included; multipart works |
| MSW layer | Every endpoint served; 7 scenarios switchable; same handlers in Vitest and Playwright |
| Primitives | Kitchen-sink route renders all variants; keyboard-focusable; tokens only |
| SchemaForm | Every field type validated; works unchanged for all 6 goal schemas and all FORM actions |
| AppShell | Sidebar 4 items + active state; drawer under 768px; header matches reference |
| Screens 1–10 | Reference-matched · all 6 packs · loading/error/empty · keyboard · 375/768/1440 · Vitest test · no banned words |
| ProgressRing | Correct arc and count; `aria-label`; test proves no `%` and no "score" |
| JourneyDiff | One component green on both preview and applied fixtures |
| NeedsReviewCard | Exactly one question; bounded answers; posts to `/clarifications` |
| Error surface | All 9 codes reachable via `?scenario=` and handled per contract §5.1 |
| Responsive | Golden path completable at 375px |
| A11y | Keyboard-only golden path; axe clean; status never colour-only |
| Test suite | ~40 Vitest + 7 Playwright, green in CI without a backend |
| Build | Production bundle deployed; dev badges off; hits the real API through the proxy |
