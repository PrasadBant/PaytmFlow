/**
 * LIVE-BACKEND E2E — runs only via playwright.live.config.ts.
 *
 * Every test creates its own journey(s) through the real API in its own
 * browser context (its own pf_session cookie), so tests never share state and
 * never rely on MSW fixture IDs. API calls made with `page.request` share the
 * page's cookies, i.e. they act as the same customer as the UI.
 */

import { test, expect, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { LIVE_REVIEWER_CODE } from "./live-env";

const DEMO_DOCS = fileURLToPath(new URL("../../public/demo-documents", import.meta.url));
const SALARY_SLIP = "sample-salary-slip.pdf";
const OFFER_LETTER = "sample-offer-letter.pdf";

const GOAL = { loan_amount: 250000, loan_purpose: "EDUCATION", tenure_months: 36 };

interface Journey {
  journey_id: string;
  snapshot_id: string;
  readiness: string;
  progress: { completed: number; total: number };
  fields: { key: string; status: string }[];
}

async function api<T>(res: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  expect(res.ok(), `${res.url()} -> ${res.status()} ${await res.text()}`).toBe(true);
  return (await res.json()) as T;
}

async function createJourney(request: APIRequestContext): Promise<Journey> {
  return api<Journey>(
    await request.post("/api/v1/journeys", { data: { journey_type: "LENDING", goal: GOAL } })
  );
}

async function getJourney(request: APIRequestContext, id: string): Promise<Journey> {
  return api<Journey>(await request.get(`/api/v1/journeys/${id}`));
}

async function applyAction(
  request: APIRequestContext,
  j: Journey,
  actionId: string,
  input: Record<string, unknown>
): Promise<Journey> {
  const body = await api<{ journey: Journey }>(
    await request.post(`/api/v1/journeys/${j.journey_id}/actions`, {
      data: {
        action_id: actionId,
        expected_snapshot_id: j.snapshot_id,
        idempotency_key: randomUUID(),
        input,
      },
    })
  );
  return body.journey;
}

async function uploadEvidence(
  request: APIRequestContext,
  j: Journey,
  docType: string,
  file: string
): Promise<string> {
  const body = await api<{ evidence_id: string }>(
    await request.post(`/api/v1/journeys/${j.journey_id}/evidence`, {
      multipart: {
        doc_type: docType,
        expected_snapshot_id: j.snapshot_id,
        file: {
          name: file,
          mimeType: "application/pdf",
          buffer: readFileSync(path.join(DEMO_DOCS, file)),
        },
      },
    })
  );
  return body.evidence_id;
}

/** Drives a fresh LENDING journey to READY with the real document pipeline. */
async function completeJourney(request: APIRequestContext, j: Journey): Promise<Journey> {
  const income = await uploadEvidence(request, j, "SALARY_SLIP", SALARY_SLIP);
  j = await applyAction(request, j, "UPLOAD_INCOME_PROOF", { evidence_id: income });
  j = await applyAction(request, j, "SUBMIT_EMPLOYMENT_INFO", { employment_type: "SALARIED" });
  const employer = await uploadEvidence(request, j, "OFFER_LETTER", OFFER_LETTER);
  j = await applyAction(request, j, "UPLOAD_WORK_ID", { evidence_id: employer });
  return applyAction(request, j, "ACCEPT_LOAN_TERMS", { accept_terms: true });
}

/** A second, independent customer: new context, so a new pf_session cookie. */
async function freshPage(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  return context.newPage();
}

test.describe("Live backend — suite guard", () => {
  test("runs against the real API with no mock service worker", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("screen-01-home")).toBeVisible();
    const workers = await page.evaluate(async () =>
      (await navigator.serviceWorker.getRegistrations()).map(
        (r) => r.active?.scriptURL ?? r.installing?.scriptURL ?? ""
      )
    );
    expect(workers.filter((u) => u.includes("mockServiceWorker"))).toEqual([]);

    // The backend, not a fixture, answers: health comes from the live FastAPI app.
    const health = await api<{ status: string; db: boolean }>(
      await page.request.get("/api/v1/health")
    );
    expect(health.db).toBe(true);
  });
});

test.describe("Live backend — customer journey", () => {
  test("creating a journey through the goal form persists a real journey", async ({ page }) => {
    await page.goto("/start/LENDING");
    await expect(page.getByTestId("screen-03-goal-basic-info")).toBeVisible();
    await page.locator("#customer-email-input").fill("e2e-live@example.com");
    await page.getByRole("button", { name: /Continue/i }).click();

    await page.waitForURL(/\/j\/[0-9a-f-]{36}$/);
    const id = page.url().split("/j/")[1];
    await expect(page.getByTestId("screen-04-current-status")).toBeVisible();

    const j = await getJourney(page.request, id);
    expect(j.journey_id).toBe(id);
    expect(j.readiness).toBe("NOT_READY");
  });

  test("status screen renders the backend's own progress for this journey", async ({ page }) => {
    const j = await createJourney(page.request);
    await page.goto(`/j/${j.journey_id}`);
    await expect(page.getByTestId("screen-04-current-status")).toBeVisible();
    await expect(page.getByText(`${j.progress.completed} Completed`)).toBeVisible();
    await expect(page.locator('[data-testid^="blocker-card-"]').first()).toBeVisible();
  });

  test("uploading a real salary slip and applying it satisfies monthly income", async ({ page }) => {
    const j = await createJourney(page.request);
    await page.goto(`/j/${j.journey_id}/act/UPLOAD_INCOME_PROOF`);
    await expect(page.getByTestId("screen-06-upload-evidence")).toBeVisible();
    await page.setInputFiles('[data-testid="evidence-file-input"]', path.join(DEMO_DOCS, SALARY_SLIP));
    await page.getByTestId("doc-type-select").selectOption("SALARY_SLIP");
    await page.getByTestId("upload-submit-btn").click();

    await expect(page.getByTestId("screen-07-ai-analysis")).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText(/85,000/).first()).toBeVisible();
    await page.getByTestId("continue-apply-btn").click();
    await expect(page.getByTestId("screen-08-updated-status")).toBeVisible();

    const after = await getJourney(page.request, j.journey_id);
    expect(after.snapshot_id).not.toBe(j.snapshot_id);
    expect(after.fields.find((f) => f.key === "monthly_income")?.status).toBe("SATISFIED");
  });

  test("a journey completed with real documents shows the completion checklist", async ({ page }) => {
    const done = await completeJourney(page.request, await createJourney(page.request));
    expect(done.readiness).toBe("READY");

    await page.goto(`/j/${done.journey_id}/complete`);
    await expect(page.getByTestId("screen-09-complete-journey")).toBeVisible();
    await expect(page.getByTestId("verification-checklist-section")).toBeVisible();
    await expect(page.getByTestId("not-ready-guard-banner")).toHaveCount(0);
  });

  test("an unfinished journey cannot be shown as complete", async ({ page }) => {
    const j = await createJourney(page.request);
    await page.goto(`/j/${j.journey_id}/complete`);
    await expect(page.getByTestId("not-ready-guard-banner")).toBeVisible();
  });

  test("My Journeys resumes this session's journey and never lists another session's", async ({
    page,
    browser,
  }) => {
    const mine = await createJourney(page.request);
    await applyAction(page.request, mine, "SUBMIT_EMPLOYMENT_INFO", { employment_type: "SALARIED" });
    const stranger = await freshPage(browser);
    const theirs = await createJourney(stranger.request);

    await page.goto("/my-journeys");
    await expect(page.getByTestId("screen-10-my-journeys")).toBeVisible();
    await expect(page.getByTestId(`journey-row-${mine.journey_id}`)).toBeVisible();
    await expect(page.getByTestId(`journey-row-${theirs.journey_id}`)).toHaveCount(0);

    await page.getByTestId(`resume-btn-${mine.journey_id}`).click();
    await page.waitForURL(new RegExp(`/j/${mine.journey_id}`));
    await expect(
      page
        .locator(
          '[data-testid="screen-04-current-status"], [data-testid="screen-05-recommendation"], [data-testid="screen-06-upload-evidence"], [data-testid="screen-08-updated-status"]'
        )
        .first()
    ).toBeVisible();

    // Direct access to another session's journey is refused by the backend.
    expect((await page.request.get(`/api/v1/journeys/${theirs.journey_id}`)).status()).toBe(404);
    await stranger.context().close();
  });
});

test.describe("Live backend — reviewer workflow", () => {
  async function openCase(customer: APIRequestContext): Promise<string> {
    const j = await createJourney(customer);
    // Local-only setup shortcut: an evidence-less mismatch report opens a review
    // case. Production (APP_ENV outside local/ci) refuses this, see the backend tests.
    await applyAction(customer, j, "UPLOAD_INCOME_PROOF", {
      monthly_income: 60000,
      ambiguity_id: "INCOME_MISMATCH",
    });
    return j.journey_id;
  }

  async function promote(page: Page, code: string): Promise<string[]> {
    const dialogs: string[] = [];
    page.on("dialog", (d) => {
      dialogs.push(`${d.type()}:${d.message()}`);
      void (d.type() === "prompt" ? d.accept(code) : d.accept());
    });
    await page.goto("/");
    await page.getByTestId("prototype-role-switch").click();
    return dialogs;
  }

  test("a wrong access code is refused and grants no reviewer access", async ({ page }) => {
    const dialogs = await promote(page, "definitely-wrong-code");
    await expect.poll(() => dialogs.some((d) => d.startsWith("alert:"))).toBe(true);
    expect((await page.request.get("/api/v1/review/cases")).status()).toBe(403);
  });

  test("a reviewer with the code claims and resolves a real case", async ({ page, browser }) => {
    const customer = await freshPage(browser);
    const journeyId = await openCase(customer.request);

    await promote(page, LIVE_REVIEWER_CODE);
    await page.waitForURL(/\/review/);
    const cases = await api<{ cases: { case_id: string; journey_id: string }[] }>(
      await page.request.get("/api/v1/review/cases")
    );
    const target = cases.cases.find((c) => c.journey_id === journeyId);
    expect(target, "review case for the new journey").toBeTruthy();
    const caseId = target!.case_id;

    await page.goto("/review/queue");
    await page.getByTestId(`review-case-row-${caseId}`).click();
    await expect(page.getByTestId("review-case-detail")).toBeVisible();
    await page.getByRole("button", { name: "Claim Case" }).click();

    await page.getByTestId("resolution-type-select").selectOption("EVIDENCE_SUFFICIENT");
    await page.getByTestId("resolution-value-input").fill("60000");
    await page.getByTestId("resolution-reason-input").fill("Salary slip matches the declared income.");
    await page.getByTestId("submit-resolution-btn").click();
    await page.getByTestId("confirm-resolution-btn").click();

    await expect
      .poll(
        async () =>
          (await api<{ status: string }>(await page.request.get(`/api/v1/review/cases/${caseId}`)))
            .status
      )
      .toBe("RESOLVED");

    // The customer never gains reviewer access from any of this.
    expect((await customer.request.get("/api/v1/review/cases")).status()).toBe(403);
    await customer.context().close();
  });
});
