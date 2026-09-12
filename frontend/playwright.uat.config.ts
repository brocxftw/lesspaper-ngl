import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.UAT_ORIGIN ?? "http://localhost:9398";
const runId = process.env.UAT_RUN_ID ?? new Date().toISOString().replace(/[:.]/g, "-");

export default defineConfig({
  testDir: "../uat/tests",
  outputDir: `../uat/artifacts/${runId}`,
  // Leave headroom for state polling and failure-evidence collection.
  timeout: Number(process.env.UAT_TIMEOUT_MS ?? 180_000),
  expect: { timeout: 15_000 },
  fullyParallel: false,
  // The local compose profile has one worker by default; parallel UAT files would
  // make readiness timings measure queue contention instead of product behaviour.
  workers: 1,
  grepInvert: process.env.UAT_AI_PROFILE === "disabled" ? /AI enabled/ : undefined,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [["./uat-reporter.ts"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 15_000,
  },
  projects: [{ name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } }],
});
