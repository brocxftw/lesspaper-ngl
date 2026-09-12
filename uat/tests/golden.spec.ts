import path from "node:path";
import { test, expect } from "../helpers/evidence";
import { UatApi, login, waitForDocument } from "../helpers/api";

test.describe.configure({ mode: "serial" });
let api: UatApi;
let documentId = "";
let folderId = "";
const fixture = path.resolve("uat/fixtures/plain-text-document.txt");

test.beforeEach(async ({ page, context }) => { await login(page); api = new UatApi(page.request, context); });

test("UAT-001 Login reaches Inbox", async ({ page }) => { await expect(page).toHaveURL(/\/inbox/); });

test("UAT-002 Logout invalidates protected routes", async ({ page }) => {
  const response = await page.request.post("/api/auth/logout", { headers: { "X-CSRF-Token": (await page.context().cookies()).find((c) => c.name === "folium_csrf")!.value } });
  expect(response.ok()).toBeTruthy();
  await page.goto("/inbox");
  await expect(page).toHaveURL(/\/login/);
});

test("UAT-010 / UAT-020 Upload native document reaches Inbox Ready to process", async () => {
  const doc = await api.upload(fixture); documentId = doc.id;
  const ready = await waitForDocument(api, doc.id, (d) => d.text_extracted && d.inbox && d.inbox_status === "ready", "Inbox Ready to process with text extracted");
  expect(ready.processing_error).toBeNull();
});

test("UAT-021 / UAT-030 Manual filing without AI processes to Library", async () => {
  expect(documentId, "UAT-010 must create the document").toBeTruthy();
  folderId = (await api.folder(`UAT-${Date.now()}`)).id;
  await api.setMetadata(documentId, folderId);
  await api.process(documentId);
  const processed = await waitForDocument(api, documentId, (d) => !d.inbox && d.document_indexed && !d.is_trashed, "processed document in Library and Keyword ready");
  expect(processed.folder_id).toBe(folderId);
});

test("UAT-040 Browse Library retains processed metadata", async ({ page }) => {
  const doc = await api.document(documentId);
  expect(doc.inbox).toBeFalsy(); expect(doc.folder_id).toBe(folderId);
  await page.goto("/library");
  await expect(page).not.toHaveURL(/\/login/);
});

test("UAT-050 Keyword search retrieves deterministic evidence without AI", async () => {
  const results = await api.search("blue-orchid-741");
  expect(results.items.some((item) => item.document_id === documentId || item.id === documentId)).toBeTruthy();
});

test("UAT-080 / UAT-081 Trash and restore keep document recoverable", async () => {
  const trashed = await api.trash(documentId); expect(trashed.is_trashed).toBeTruthy();
  const restored = await api.restore(documentId); expect(restored.is_trashed).toBeFalsy(); expect(restored.inbox).toBeFalsy();
});
