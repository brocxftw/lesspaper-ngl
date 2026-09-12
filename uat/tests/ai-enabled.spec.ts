import path from "node:path";
import { test, expect } from "../helpers/evidence";
import { UatApi, login, waitForDocument } from "../helpers/api";

test.describe.configure({ mode: "serial" });
let api: UatApi;
let documentId = "";
const documentIds: string[] = [];
const suggestionFixture = path.resolve("../uat/fixtures/ai-suggestion-document.txt");
const semanticFixture = path.resolve("../uat/fixtures/ai-semantic-document.txt");
const enabled = process.env.UAT_AI_PROFILE === "enabled";

async function processedDocument(requireEmbeddings = false) {
  const doc = await api.upload(semanticFixture); documentId = doc.id; documentIds.push(doc.id);
  await waitForDocument(api, doc.id, (d) => d.text_extracted && d.inbox, "completed Inbox Preflight");
  const folder = await api.folder(`UAT-AI-${Date.now()}`);
  await api.setMetadata(doc.id, folder.id);
  await api.process(doc.id);
  return waitForDocument(api, doc.id, (d) => !d.inbox && d.document_indexed && (!requireEmbeddings || d.has_embeddings), requireEmbeddings ? "Semantic ready" : "Keyword ready");
}

test.beforeEach(async ({ page, context }) => { await login(page); api = new UatApi(page.request, context); });

test("UAT-022 AI enabled filing suggestion remains non-canonical until accepted", async () => {
  test.skip(!enabled, "Requires --ai=enabled");
  const [capabilities, assignments] = await Promise.all([api.capabilities(), api.assignments()]);
  test.skip(!capabilities.auto_tagging || !assignments.some((a) => a.role === "indexing" && a.status === "configured"), "No configured metadata-suggestion capability");
  const doc = await api.upload(suggestionFixture); documentId = doc.id; documentIds.push(doc.id);
  await waitForDocument(api, doc.id, (d) => d.text_extracted && d.inbox, "completed Inbox Preflight");
  const deadline = Date.now() + 120_000;
  let pending: Awaited<ReturnType<UatApi["suggestions"]>> = [];
  while (Date.now() < deadline && pending.length === 0) { pending = (await api.suggestions(doc.id)).filter((s) => s.status === "pending"); if (!pending.length) await new Promise((r) => setTimeout(r, 750)); }
  expect(pending, "configured suggestion provider returned no pending suggestion").not.toHaveLength(0);
  const accepted = await api.acceptSuggestion(pending[0].id);
  expect(accepted.status).toBe("accepted");
});

test("UAT-051 AI enabled Semantic search retrieves Semantic ready evidence", async () => {
  test.skip(!enabled, "Requires --ai=enabled");
  const capabilities = await api.capabilities();
  test.skip(!capabilities.embeddings_available, "No embedding provider configured");
  await processedDocument(true);
  const results = await api.search("blue orchid retrieval code", "semantic");
  expect(results.effective_mode).toBe("semantic");
  expect(results.items.some((item) => item.document?.id === documentId)).toBeTruthy();
});

test("UAT-052 AI enabled Evidence search does not require Ask", async () => {
  test.skip(!enabled, "Requires --ai=enabled");
  expect(documentId, "UAT-051 must prepare evidence").toBeTruthy();
  const before = await api.usage();
  const results = await api.search("blue-orchid-741", "keyword");
  expect(results.items.some((item) => item.document?.id === documentId)).toBeTruthy();
  const after = await api.usage();
  const chatRequests = (usage: typeof after) => usage.by_workload.find((entry) => entry.key === "chat")?.requests ?? 0;
  expect(chatRequests(after)).toBe(chatRequests(before));
});

test("UAT-070 AI enabled Ask current document returns cited evidence", async () => {
  test.skip(!enabled, "Requires --ai=enabled");
  const capabilities = await api.capabilities();
  test.skip(!capabilities.chat_available, "No chat provider configured");
  expect(documentId, "UAT-051 must prepare the document").toBeTruthy();
  const answer = await api.ask({ question: "What amount is due?", scope: "document", document_id: documentId, confirm_remote: capabilities.warn_before_remote_chat });
  expect(answer.insufficient_evidence).toBeFalsy();
  expect(answer.answer).toMatch(/123\.45|RM\s*123/i);
  expect(answer.citations.some((citation) => citation.document_id === documentId)).toBeTruthy();
});

test("UAT-071 AI enabled Ask reports insufficient evidence", async () => {
  test.skip(!enabled, "Requires --ai=enabled");
  const capabilities = await api.capabilities();
  test.skip(!capabilities.chat_available, "No chat provider configured");
  const answer = await api.ask({ question: "What is the customer shoe size?", scope: "document", document_id: documentId, confirm_remote: capabilities.warn_before_remote_chat });
  expect(answer.insufficient_evidence).toBeTruthy();
  expect(answer.citations).toHaveLength(0);
});

test.afterAll(async ({ browser }) => {
  if (!documentIds.length) return;
  const context = await browser.newContext(); const page = await context.newPage();
  try { await login(page); const cleanup = new UatApi(page.request, context); for (const id of documentIds) await cleanup.permanentlyDelete(id); } finally { await context.close(); }
});
