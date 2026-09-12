import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.UAT_ORIGIN ?? "http://localhost:9398";
const runId = process.env.UAT_RUN_ID ?? new Date().toISOString().replace(/[:.]/g, "-");

export default defineConfig({
  testDir: "../uat/tests",
  outputDir: `../uat/artifacts/${runId}`,
  timeout: Number(process.env.UAT_TIMEOUT_MS ?? 90_000),
  expect: { timeout: 15_000 },
  fullyParallel: false,
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
