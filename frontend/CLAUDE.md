# PaytmFlow Frontend — Agent Context

## What this is
Applicant-facing UI for a financial-journey recovery platform. 10 screens defined by
`00_SHARED_CONTRACT.md` and `01_DEV1_FRONTEND_PLAN.md`.

## Absolute rules — violating any of these is a build failure
1. NEVER render a percentage, gauge, dial, or the words score / approval / probability /
   eligibility / guaranteed. The progress ring is "3/7 Completed" and nothing else.
2. NEVER implement business logic. No computing blocked status, no deciding next actions,
   no currency formatting. The API supplies `label`, `display_value`, `explanation`,
   ordering and `resume_screen`. Render what you're given.
3. NEVER branch on journey type. No `if (journeyType === 'LENDING')`. All six journeys use
   the same components, driven by `goal_schema`, `input_schema` and `ui_labels`.
4. NEVER use dangerouslySetInnerHTML. AI-written strings reach the screen; render as text.
5. NEVER edit `src/api/types.gen.ts` — regenerate with `make types` or `npm run codegen:types`.
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
keyboard-navigable · works at 375/768/1440 · matches reference specifications ·
Vitest test exists · no banned words.

## Commands
npm run dev · npm run test · npm run test:e2e · npm run lint · npm run typecheck · npm run codegen:types
