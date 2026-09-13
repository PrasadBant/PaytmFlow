import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for PaytmFlow frontend E2E tests.
 *
 * Tests run against MSW-intercepted requests — no live backend required.
 * The dev server is started by Playwright webServer configuration.
 *
 * Scenarios are controlled via ?scenario=<name> query param or sessionStorage,
 * matching the same mechanism as Vitest unit tests.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",

  /* Parallel workers — sequential within each spec file */
  workers: 1,
  fullyParallel: false,

  /* Fail CI fast on any unexpected failure */
  forbidOnly: !!process.env.CI,

  /* Retry once in CI to handle transient flakes */
  retries: process.env.CI ? 1 : 0,

  /* Reporter: list for local, GitHub Actions annotation in CI */
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],

  use: {
    /* Base URL — Playwright prepends this to page.goto calls */
    baseURL: "http://localhost:5173",

    /* Always capture traces on first retry */
    trace: "on-first-retry",

    /* Screenshots on failure */
    screenshot: "only-on-failure",

    /* Headless by default; set PWDEBUG=1 to open headed */
    headless: !process.env.PWDEBUG,

    /* Timeouts */
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },

  projects: [
    {
      name: "chromium-desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: "mobile-chrome",
      use: {
        ...devices["Pixel 5"],
        viewport: { width: 375, height: 812 },
      },
    },
  ],

  /* Start the Vite dev server before running tests */
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
