import { defineConfig, devices } from "@playwright/test";
import { LIVE_REVIEWER_CODE } from "./tests/e2e-live/live-env";

/**
 * LIVE-BACKEND E2E (npm run test:e2e:live).
 *
 * Unlike playwright.config.ts (MSW mocks, fixture journey IDs), this starts a
 * real FastAPI backend against the local PostgreSQL from backend/.env and a
 * Vite dev server with VITE_API_MODE=live. Every test creates its own
 * journeys through the real API, so nothing depends on fixture IDs.
 *
 * Dedicated ports (8010 / 5180) and reuseExistingServer: false guarantee a
 * mock-mode dev server on 5173 can never be picked up by mistake.
 *
 * Backend overrides: no outbound notifications or cloud AI (N8N/Sarvam off),
 * the real local OCR/classifier pipeline for documents, and a test-only
 * reviewer access code so the reviewer prompt is exercised for real.
 */

const BACKEND_PORT = 8010;
const FRONTEND_PORT = 5180;

export default defineConfig({
  testDir: "./tests/e2e-live",
  testMatch: "**/*.live.spec.ts",
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [["list"]],
  timeout: 90_000,

  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    headless: !process.env.PWDEBUG,
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
  },

  projects: [
    {
      name: "live-chromium-desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],

  webServer: [
    {
      command: `uv run --directory ../backend alembic upgrade head && uv run --directory ../backend uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT} --loop none`,
      url: `http://127.0.0.1:${BACKEND_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "ignore",
      stderr: "pipe",
      env: {
        APP_ENV: "local",
        AI_PROVIDER: "local_ml",
        N8N_ENABLED: "false",
        SARVAM_ENABLED: "false",
        REVIEWER_ACCESS_CODE: LIVE_REVIEWER_CODE,
      },
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      url: `http://localhost:${FRONTEND_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: "pipe",
      stderr: "pipe",
      env: {
        VITE_API_MODE: "live",
        PF_API_PROXY_TARGET: `http://127.0.0.1:${BACKEND_PORT}`,
      },
    },
  ],
});
