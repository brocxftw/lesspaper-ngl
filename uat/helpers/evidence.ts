import { test as base } from "../../frontend/node_modules/@playwright/test";
import { writeFile } from "node:fs/promises";

export const test = base.extend<{ evidence: void }>({
  evidence: [async ({ page }, use, testInfo) => {
    const consoleEvents: unknown[] = [];
    const failedRequests: unknown[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleEvents.push({ type: message.type(), text: message.text() });
    });
    page.on("requestfailed", (request) => failedRequests.push({ url: request.url(), method: request.method(), failure: request.failure()?.errorText }));
    page.on("response", (response) => {
      if (response.status() >= 400) failedRequests.push({ url: response.url(), status: response.status(), method: response.request().method() });
    });
    await use();
    if (testInfo.status !== testInfo.expectedStatus) {
      await writeFile(testInfo.outputPath("console.log"), consoleEvents.map(JSON.stringify).join("\n"));
      await writeFile(testInfo.outputPath("network.json"), JSON.stringify(failedRequests, null, 2));
      // The API stores redacted structured logs. Keep only a bounded recent window;
      // an unavailable log endpoint must not obscure the original test failure.
      for (const service of ["api", "worker"] as const) {
        try {
          const response = await page.request.get(`/api/logs?range=1h&page_size=50&service=${service}`);
          if (response.ok()) await writeFile(testInfo.outputPath(`${service === "api" ? "backend" : "worker"}.log`), JSON.stringify(await response.json(), null, 2));
        } catch { /* evidence is best effort */ }
      }
      await testInfo.attach("console.log", { path: testInfo.outputPath("console.log"), contentType: "text/plain" });
      await testInfo.attach("network.json", { path: testInfo.outputPath("network.json"), contentType: "application/json" });
    }
  }, { auto: true }],
});
export { expect } from "../../frontend/node_modules/@playwright/test";
