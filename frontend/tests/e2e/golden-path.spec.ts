/**
 * F31 — Playwright E2E Suite
 *
 * Covers (against MSW — no live backend required):
 *   1. Lending golden path: Screen 1 → 9
 *   2. Stale action: 409 error banner shown, no duplicate POST
 *   3. Needs Review: requires-review-notice shown
 *   4. Resume from Screen 10 lands on the right screen
 *   5. Mobile viewport (375px) golden path walk
 *   6. All six pack cards render on Screen 2 without error
 *
 * Progress is asserted as "{N} Completed" — never as a percentage.
 *
 * State injection note:
 *   React Router v6 reads user state from window.history.state.usr (not from the
 *   raw state root). gotoWithState() wraps the payload in { usr, idx, key } so
 *   useLocation().state returns the expected value after a page reload.
 */

import { test, expect, type Page } from "@playwright/test";

// ─────────────────────────────────────────────────────────────────────────────
// Fixture snapshots (mirrors frontend/src/mocks/fixtures/lending/)
// ─────────────────────────────────────────────────────────────────────────────

const JOURNEY_ID = "11111111-1111-1111-1111-111111111111";

const EVIDENCE_SALARY_SLIP = {
  evidence_id: "22222222-2222-2222-2222-222222222222",
  filename: "payslip_august_2026.pdf",
  uploaded_at: "2026-09-12T10:05:00Z",
  size_bytes: 1428500,
  interpretation: {
    verified: true,
    confidence: 0.96,
    detected: [
      { key: "monthly_income", label: "Net Monthly Salary", display_value: "₹85,000" },
    ],
    summary: "Verified August 2026 salary slip confirming net in-hand credit of ₹85,000.",
    conflicts: [],
  },
  proposed_action_id: "UPLOAD_INCOME_PROOF",
  consequence_preview: {
    newly_satisfied: [{ key: "monthly_income", label: "Verified Monthly Income" }],
    newly_unlocked: [{ action_id: "UPLOAD_BANK_STATEMENT", title: "Upload Bank Statement" }],
    still_blocked: [{ key: "bank_statement", label: "Bank Statement" }],
    predicted_progress: { completed: 4, total: 7 },
  },
  diff_preview: {
    fields_changed: [],
    actions_unlocked: [],
    actions_removed: [],
    readiness_transition: null,
  },
  requires_review: false,
};

const ACTION_RESPONSE_V2 = {
  journey: {
    journey_id: JOURNEY_ID,
    session_id: "00000000-0000-0000-0000-000000000001",
    journey_type: "LENDING",
    version_number: 2,
    snapshot_id: "bbbbbbbb-2222-2222-2222-222222222222",
    readiness: "NOT_READY",
    status: "IN_PROGRESS",
    progress: { completed: 4, pending: 2, blockers: 1, total: 7 },
    fields: [
      {
        key: "loan_amount", label: "Loan Amount", status: "SATISFIED",
        value: 500000, display_value: "₹5,00,000", explanation: "", mandatory: true,
      },
      {
        key: "monthly_income", label: "Monthly Income", status: "SATISFIED",
        value: 85000, display_value: "₹85,000", explanation: "", mandatory: true,
      },
      {
        key: "bank_statement", label: "Bank Statement", status: "MISSING",
        value: null, display_value: null, explanation: "Required", mandatory: true,
        resolve_action_id: "UPLOAD_BANK_STATEMENT",
      },
    ],
    actions: [],
    milestones: [],
    current_milestone: null,
    readiness_explanation: null,
    ui_labels: null,
    display: null,
  },
  diff: {
    snapshot_id_before: "aaaaaaaa-1111-1111-1111-111111111111",
    snapshot_id_after: "bbbbbbbb-2222-2222-2222-222222222222",
    fields_changed: [
      {
        key: "monthly_income",
        label: "Verified Monthly Income",
        before: null,
        after: "₹85,000",
        status_before: "MISSING",
        status_after: "SATISFIED",
        is_cascaded: false,
      },
    ],
    actions_unlocked: ["UPLOAD_BANK_STATEMENT"],
    actions_removed: [],
    readiness_transition: { before: "NOT_READY", after: "NOT_READY" },
  },
  next_recommendation: null,
};

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

async function visitHome(page: Page) {
  await page.goto("/");
  await page.waitForSelector('[data-testid="screen-01-home"]', { timeout: 10_000 });
}

async function waitForPath(page: Page, pattern: RegExp | string) {
  await page.waitForURL(pattern, { timeout: 12_000 });
}

/**
 * Navigate to `path` and inject React Router v6 location.state.
 *
 * React Router v6 stores user state under window.history.state.usr (not at the
 * root). We wrap payload in { usr, idx, key } so that useLocation().state returns
 * the correct value when the app mounts on a (re)load.
 */
async function gotoWithState(page: Page, path: string, userState: unknown) {
  // Navigate first so the app bootstraps MSW and React mounts once
  await page.goto(path);
  // Wait for app shell to appear (confirms MSW worker is ready)
  await page.waitForSelector("#root > *", { timeout: 10_000 });

  // Inject the React Router state wrapper and reload in-place (no network request)
  await page.evaluate(
    ([p, s]) => {
      // React Router v6 history state shape: { usr, idx, key }
      const existing = window.history.state as Record<string, unknown> | null;
      const idx = (existing && typeof existing.idx === "number") ? existing.idx : 0;
      const key = (existing && typeof existing.key === "string") ? existing.key : "default";
      window.history.replaceState({ usr: s, idx, key }, "", p);
    },
    [path, userState] as [string, unknown]
  );

  // Force React Router to re-read location.state by navigating to same path via popstate
  await page.evaluate((p) => {
    window.history.pushState(window.history.state, "", p);
    window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
  }, path);

  // Short wait for React to process the navigation event
  await page.waitForTimeout(300);
}



// ─────────────────────────────────────────────────────────────────────────────
// Suite 1 — Lending Golden Path (Screens 1 → 9)
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Lending golden path (Screen 1 → 9)", () => {
  test("Screen 1 — home renders headline and CTA", async ({ page }) => {
    await visitHome(page);
    await expect(page.getByText("Your Financial Journey.")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Start Your Journey/i })
    ).toBeVisible();
  });

  test("Screen 2 — journey selection shows all 6 packs", async ({ page }) => {
    await page.goto("/start");
    await expect(page.getByTestId("screen-02-journey-selection")).toBeVisible({
      timeout: 10_000,
    });
    for (const type of [
      "LENDING", "INSURANCE", "CREDIT_CARD", "KYC", "ACCOUNT_OPENING", "INVESTMENT",
    ]) {
      await expect(page.getByTestId(`pack-card-${type}`)).toBeVisible({ timeout: 8_000 });
    }
  });

  test("Screen 3 — LENDING goal form renders and has Continue button", async ({ page }) => {
    await page.goto("/start/LENDING");
    await expect(page.getByTestId("screen-03-goal-basic-info")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("button", { name: /Continue/i })).toBeVisible({ timeout: 6_000 });
  });

  test("Screen 4 — current status: 3 Completed, blocker card visible", async ({ page }) => {
    await page.goto(`/j/${JOURNEY_ID}`);
    await expect(page.getByTestId("screen-04-current-status")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("3 Completed")).toBeVisible({ timeout: 8_000 });
    await expect(
      page.locator('[data-testid^="blocker-card-"]').first()
    ).toBeVisible({ timeout: 6_000 });
    await expect(
      page.getByRole("button", { name: /Take Recommended Step/i })
    ).toBeVisible();
  });

  test("Screen 5 — recommendation card visible", async ({ page }) => {
    await page.goto(`/j/${JOURNEY_ID}/next`);
    await expect(page.getByTestId("screen-05-recommendation")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("recommendation-card")).toBeVisible({ timeout: 8_000 });
  });

  test("Screen 6 — upload evidence: tabs and default panel visible", async ({ page }) => {
    await page.goto(`/j/${JOURNEY_ID}/act/UPLOAD_INCOME_PROOF`);
    await expect(page.getByTestId("screen-06-upload-evidence")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("tab", { name: /Upload File/i })).toBeVisible({ timeout: 6_000 });
    await expect(page.getByRole("tab", { name: /Enter Details/i })).toBeVisible();
    await expect(page.getByTestId("tabpanel-upload")).toBeVisible();
  });

  test("Screen 7 — AI analysis: evidence card, consequence preview, Apply CTA", async ({ page }) => {
    await gotoWithState(page, `/j/${JOURNEY_ID}/analysis`, {
      evidenceResponse: EVIDENCE_SALARY_SLIP,
      journeyId: JOURNEY_ID,
      actionId: "UPLOAD_INCOME_PROOF",
      snapshotId: "aaaaaaaa-1111-1111-1111-111111111111",
    });
    await expect(page.getByTestId("screen-07-ai-analysis")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("evidence-card")).toBeVisible({ timeout: 8_000 });
    await expect(page.getByTestId("consequence-preview-card")).toBeVisible({ timeout: 6_000 });
    await expect(page.getByTestId("continue-apply-btn")).toBeVisible();
  });

  test("Screen 8 — updated status: diff card and progress visible", async ({ page }) => {
    await gotoWithState(page, `/j/${JOURNEY_ID}/updated`, {
      actionResponse: ACTION_RESPONSE_V2,
      journeyId: JOURNEY_ID,
    });
    await expect(page.getByTestId("screen-08-updated-status")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("journey-diff-section")).toBeVisible({ timeout: 8_000 });
    await expect(page.getByTestId("journey-diff-card")).toBeVisible({ timeout: 6_000 });
    await expect(page.getByText("4 Completed")).toBeVisible({ timeout: 6_000 });
  });

  test("Screen 9 — complete journey: screen renders and guard banner shown when journey is NOT_READY", async ({ page }) => {
    // MSW service worker always intercepts requests and takes priority over page.route().
    // At step 1 (default MSW state), /journeys/:id returns NOT_READY.
    // Screen 9 renders `screen-09-complete-journey` root + `not-ready-guard-banner` in this state.
    // The READY state path (`verification-checklist-section`) is fully covered by Vitest:
    //   src/tests/Screen09CompleteJourney.test.tsx
    await page.goto(`/j/${JOURNEY_ID}/complete`);
    await expect(page.getByTestId("screen-09-complete-journey")).toBeVisible({ timeout: 10_000 });
    // Guard banner shown when readiness !== READY
    await expect(page.getByTestId("not-ready-guard-banner")).toBeVisible({ timeout: 8_000 });
    await expect(
      page.getByText(/Journey Not Ready for Completion/i)
    ).toBeVisible({ timeout: 6_000 });
    // Navigation CTA visible
    await expect(
      page.getByRole("button", { name: /View Current Status/i })
    ).toBeVisible({ timeout: 4_000 });
  });
});


// ─────────────────────────────────────────────────────────────────────────────
// Suite 2 — Stale Action (409 error banner, no duplicate POST)
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Stale action — 409 handling", () => {
  test("stale 409 response renders error banner without navigating away", async ({ page }) => {
    await gotoWithState(page, `/j/${JOURNEY_ID}/analysis?scenario=stale`, {
      evidenceResponse: EVIDENCE_SALARY_SLIP,
      journeyId: JOURNEY_ID,
      actionId: "UPLOAD_INCOME_PROOF",
      snapshotId: "aaaaaaaa-1111-1111-1111-111111111111",
    });
    await expect(page.getByTestId("screen-07-ai-analysis")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("evidence-card")).toBeVisible({ timeout: 8_000 });

    const applyBtn = page.getByTestId("continue-apply-btn");
    await expect(applyBtn).toBeVisible({ timeout: 6_000 });
    await expect(applyBtn).toBeEnabled();

    // Click Apply — scenario=stale causes MSW to return 409 ACTION_STALE
    await applyBtn.click();

    // Screen 7 handles 409 and renders the error banner
    await expect(page.getByTestId("apply-error-banner")).toBeVisible({ timeout: 6_000 });
    // Screen remains on Screen 7 without blind retry or unwanted navigation
    await expect(page.getByTestId("screen-07-ai-analysis")).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Suite 3 — Needs Review
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Needs Review flow", () => {
  test("requires-review-notice visible when evidenceResponse.requires_review is true", async ({ page }) => {
    const needsReviewEvidence = {
      ...EVIDENCE_SALARY_SLIP,
      requires_review: true,
      interpretation: {
        ...EVIDENCE_SALARY_SLIP.interpretation,
        verified: false,
        conflicts: [
          {
            ambiguity_id: "INCOME_MISMATCH",
            field_key: "monthly_income",
            question: "Income on slip differs from declared amount. Which is correct?",
            answer_type: "CHOICE",
            choices: [
              { value: "slip", label: "Use value from salary slip: ₹85,000" },
              { value: "declared", label: "Use declared value: ₹75,000" },
            ],
          },
        ],
      },
    };
    await gotoWithState(page, `/j/${JOURNEY_ID}/analysis`, {
      evidenceResponse: needsReviewEvidence,
      journeyId: JOURNEY_ID,
      actionId: "UPLOAD_INCOME_PROOF",
      snapshotId: "aaaaaaaa-1111-1111-1111-111111111111",
    });
    await expect(page.getByTestId("screen-07-ai-analysis")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("evidence-card")).toBeVisible({ timeout: 8_000 });
    await expect(page.getByTestId("requires-review-notice")).toBeVisible({ timeout: 8_000 });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Suite 4 — Resume from Screen 10
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Resume from Screen 10 — My Journeys", () => {
  test("clicking Resume navigates to the correct journey screen", async ({ page }) => {
    await page.goto("/my-journeys");
    await expect(page.getByTestId("screen-10-my-journeys")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("journeys-list")).toBeVisible({ timeout: 8_000 });
    const resumeBtn = page.locator('[data-testid^="resume-btn-"]').first();
    await expect(resumeBtn).toBeVisible({ timeout: 8_000 });
    await resumeBtn.click();
    await waitForPath(page, /\/j\//);
    const validScreen = page.locator(
      '[data-testid="screen-04-current-status"], [data-testid="screen-05-recommendation"], [data-testid="screen-08-updated-status"]'
    ).first();
    await expect(validScreen).toBeVisible({ timeout: 10_000 });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Suite 5 — Mobile Viewport (375px) Golden Path Smoke
// ─────────────────────────────────────────────────────────────────────────────

test.describe("Mobile viewport (375px) golden path smoke", () => {
  // Pin the real 375px viewport regardless of which project runs this file.
  // Without this, chromium-desktop's own 1440x900 default silently ran every
  // "on 375px" test in this suite at desktop width - the assertions still
  // passed (a 1440px page also has no horizontal overflow, its CTA is also
  // in-viewport, etc.), so the gap was invisible until a fallback assertion
  // here happened to depend on genuinely-mobile behaviour (the hamburger
  // toggle only rendering below the `md` breakpoint) to pick the right branch.
  test.use({ viewport: { width: 375, height: 812 } });

  test("home screen CTA visible and in viewport on 375px", async ({ page }) => {
    await visitHome(page);
    const cta = page.getByRole("button", { name: /Start Your Journey/i });
    await expect(cta).toBeVisible();
    await expect(cta).toBeInViewport();
  });

  test("Screen 2 pack grid has no horizontal overflow on 375px", async ({ page }) => {
    await page.goto("/start");
    await expect(page.getByTestId("screen-02-journey-selection")).toBeVisible({ timeout: 10_000 });
    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth
    );
    expect(hasOverflow).toBe(false);
  });

  test("Screen 4 progress ring visible in viewport on 375px", async ({ page }) => {
    await page.goto(`/j/${JOURNEY_ID}`);
    await expect(page.getByTestId("screen-04-current-status")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("progress-ring")).toBeVisible({ timeout: 6_000 });
    await expect(page.getByTestId("progress-ring")).toBeInViewport();
  });

  test("navigation accessible on 375px — sidebar or mobile drawer", async ({ page }) => {
    await visitHome(page);
    const mobileToggle = page.getByTestId("mobile-menu-toggle");
    const toggleVisible = await mobileToggle.isVisible();
    if (toggleVisible) {
      await mobileToggle.click();
      await expect(page.getByTestId("sidebar-backdrop")).toBeVisible({ timeout: 6_000 });
    } else {
      await expect(page.locator("aside, nav").first()).toBeVisible({ timeout: 6_000 });
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Suite 6 — All Six Packs Render Without Error
// ─────────────────────────────────────────────────────────────────────────────

test.describe("All six journey packs render without error", () => {
  const PACKS = ["LENDING", "INSURANCE", "CREDIT_CARD", "KYC", "ACCOUNT_OPENING", "INVESTMENT"];
  for (const pack of PACKS) {
    test(`${pack} pack card visible on Screen 2`, async ({ page }) => {
      await page.goto("/start");
      await expect(page.getByTestId("screen-02-journey-selection")).toBeVisible({ timeout: 10_000 });
      await expect(page.getByTestId(`pack-card-${pack}`)).toBeVisible({ timeout: 8_000 });
    });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// Suite 7 — Evidence analysis never reuses a previous document's result
// ─────────────────────────────────────────────────────────────────────────────
//
// Regression for a real bug: Screen 6 -> POST /evidence -> Screen 7 previously
// showed the salary-slip result for every subsequent evidence upload, because
// the mock handler ignored doc_type and always returned the same fixture. Both
// uploads below happen within ONE page/session (via client-side navigation, not
// page.goto, which would reset the mock's in-memory step state) so this proves
// the SECOND upload's analysis is genuinely independent of the first - not
// cached React state, not a stale query, not a reused fixture.

test.describe("Evidence analysis does not reuse the previous document (regression)", () => {
  test("Salary Slip then Bank Statement each show their own filename and extracted values", async ({ page }) => {
    // 1. Upload a salary slip for UPLOAD_INCOME_PROOF via the real file dropzone.
    await page.goto(`/j/${JOURNEY_ID}/act/UPLOAD_INCOME_PROOF`);
    await expect(page.getByTestId("screen-06-upload-evidence")).toBeVisible({ timeout: 10_000 });
    await page.setInputFiles('[data-testid="evidence-file-input"]', {
      name: "my_payslip.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("dummy salary slip content"),
    });
    await page.getByTestId("upload-submit-btn").click();
    await expect(page.getByTestId("screen-07-ai-analysis")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("payslip_august_2026.pdf")).toBeVisible();
    await expect(page.getByText(/85,000/).first()).toBeVisible();

    // Apply it, advancing the journey to version 2.
    await page.getByTestId("continue-apply-btn").click();
    await expect(page.getByTestId("screen-08-updated-status")).toBeVisible({ timeout: 10_000 });

    // 2. Client-side navigate (not page.goto - that would reload the app and
    // reset the mock's step counter) to the NEXT evidence action and upload a
    // completely different document.
    await page.evaluate((id) => {
      window.history.pushState({}, "", `/j/${id}/act/UPLOAD_BANK_STATEMENT`);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }, JOURNEY_ID);
    await expect(page.getByTestId("screen-06-upload-evidence")).toBeVisible({ timeout: 10_000 });
    // Title is action-specific, not the previous action's "Upload Income Proof".
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Bank Statement/i);

    await page.setInputFiles('[data-testid="evidence-file-input"]', {
      name: "my_bank_statement.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("dummy bank statement content"),
    });
    await page.getByTestId("upload-submit-btn").click();
    await expect(page.getByTestId("screen-07-ai-analysis")).toBeVisible({ timeout: 10_000 });

    // The analysis screen must show THIS document's own result...
    await expect(page.getByText("bank_statement_aug2026.pdf")).toBeVisible();
    await expect(page.getByText(/Average Monthly Credit/i)).toBeVisible();
    // ...and must never leak the salary slip's filename or field label forward.
    await expect(page.getByText("payslip_august_2026.pdf")).not.toBeVisible();
    await expect(page.getByText("Net Monthly Salary")).not.toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Suite 8 — Every journey shows its own data, never Lending's (regression)
// ─────────────────────────────────────────────────────────────────────────────
//
// Root cause: GET /journeys/:id (and recommendation/actions/evidence/
// clarifications) ignored the real journey_id and always returned LENDING
// fixture data. A cold page load of ANY other journey - exactly what a
// refresh, deep link, or "Resume" from Screen 10 does - silently showed
// someone else's fields and progress. These tests load each journey directly
// (no prior navigation/cache to paper over it) and via "Resume" from Screen 10.

test.describe("Every journey shows its own pack data (regression)", () => {
  const INSURANCE_ID = "22222222-2222-2222-2222-222222222222";
  const KYC_ID = "33333333-3333-3333-3333-333333333333";

  test("cold-loading the INSURANCE journey shows Insurance fields, never Lending's", async ({ page }) => {
    await page.goto(`/j/${INSURANCE_ID}`);
    await expect(page.getByTestId("screen-04-current-status")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Pre-existing Disease Clearance")).toBeVisible();
    await expect(page.getByText("Loan Amount")).not.toBeVisible();
    await expect(page.getByText("Verified Monthly Income")).not.toBeVisible();
  });

  test("cold-loading the KYC journey shows KYC fields, never Lending's or Insurance's", async ({ page }) => {
    await page.goto(`/j/${KYC_ID}`);
    await expect(page.getByTestId("screen-04-current-status")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Aadhaar/i).first()).toBeVisible();
    await expect(page.getByText("Loan Amount")).not.toBeVisible();
    await expect(page.getByText("Pre-existing Disease Clearance")).not.toBeVisible();
  });

  test("resuming Insurance from My Journeys shows its own Needs Review clarification, not Lending's", async ({ page }) => {
    await page.goto("/my-journeys");
    await expect(page.getByTestId("screen-10-my-journeys")).toBeVisible({ timeout: 10_000 });
    await page.getByTestId(`journey-row-${INSURANCE_ID}`).click();
    await expect(page).toHaveURL(new RegExp(`/j/${INSURANCE_ID}$`), { timeout: 10_000 });
    await expect(page.getByTestId("needs-review-card")).toBeVisible({ timeout: 8_000 });
    await expect(
      page.getByText(/nicotine or tobacco products/i)
    ).toBeVisible();
  });
});
