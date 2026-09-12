import { expect, type APIRequestContext, type BrowserContext, type Page } from "../../frontend/node_modules/@playwright/test";

export type Document = {
  id: string; title: string; original_filename: string; inbox: boolean; inbox_status: string | null;
  text_extracted: boolean; document_indexed: boolean; folder_id: string; is_trashed: boolean;
  processing_status: string; processing_error: string | null; has_embeddings: boolean;
};

export class UatApi {
  constructor(private readonly request: APIRequestContext, private readonly context: BrowserContext) {}

  private async csrf(): Promise<string> {
    const cookie = (await this.context.cookies()).find(({ name }) => name === "folium_csrf");
    if (!cookie) throw new Error("No CSRF cookie: authenticate through the Login journey first");
    return cookie.value;
  }

  async get<T>(path: string): Promise<T> {
    const response = await this.request.get(path);
    expect(response.ok(), `GET ${path}: ${response.status()} ${await response.text()}`).toBeTruthy();
    return response.json() as Promise<T>;
  }

  async post<T>(path: string, data?: unknown): Promise<T> {
    const response = await this.request.post(path, { data, headers: { "X-CSRF-Token": await this.csrf() } });
    expect(response.ok(), `POST ${path}: ${response.status()} ${await response.text()}`).toBeTruthy();
    return response.json() as Promise<T>;
  }

  async patch<T>(path: string, data?: unknown): Promise<T> {
    const response = await this.request.patch(path, { data, headers: { "X-CSRF-Token": await this.csrf() } });
    expect(response.ok(), `PATCH ${path}: ${response.status()} ${await response.text()}`).toBeTruthy();
    return response.json() as Promise<T>;
  }

  async upload(file: string): Promise<Document> {
    const response = await this.request.post("/api/documents/upload", {
      multipart: { file: { name: file.split("/").pop()!, mimeType: "text/plain", buffer: Buffer.from(await (await import("node:fs/promises")).readFile(file)) } },
      headers: { "X-CSRF-Token": await this.csrf() },
    });
    expect(response.status(), `upload: ${await response.text()}`).toBe(201);
    return response.json() as Promise<Document>;
  }

  document(id: string) { return this.get<Document>(`/api/documents/${id}`); }
  jobs(id: string) { return this.get<Array<{ status: string; job_type: string; error?: string }>>(`/api/jobs?document_id=${id}`); }
  async folder(name: string) { return this.post<{ id: string }>("/api/folders", { name }); }
  async trashFolder(id: string) { return this.post(`/api/folders/${id}/trash`); }
  async setMetadata(id: string, folder_id: string) { return this.patch<Document>(`/api/documents/${id}/metadata`, { folder_id, needs_review: false }); }
  async process(id: string) { return this.post("/api/documents/process", { document_ids: [id] }); }
  async search(query: string) { return this.post<{ items: Array<{ document?: { id: string }; snippet?: string }> }>("/api/search", { query, mode: "keyword" }); }
  async trash(id: string) { return this.post<Document>(`/api/documents/${id}/trash`); }
  async restore(id: string) { return this.post<Document>(`/api/documents/${id}/restore`); }
  async remove(id: string) { return this.post(`/api/documents/${id}/remove-from-queue`); }
}

export async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Username").fill(process.env.UAT_USERNAME ?? "admin");
  await page.locator("input#password").fill(process.env.UAT_PASSWORD ?? "changeme");
  await page.getByRole("button", { name: "Sign in" }).click();
  try {
    await expect(page).toHaveURL(/\/inbox/);
  } catch (error) {
    const message = await page.locator("body").innerText();
    if (/invalid username or password/i.test(message)) {
      throw new Error("UAT credentials rejected; set UAT_USERNAME and UAT_PASSWORD for the target environment");
    }
    throw error;
  }
}

export async function waitForDocument(
  api: UatApi, id: string, predicate: (doc: Document) => boolean, expected: string,
): Promise<Document> {
  const deadline = Date.now() + Number(process.env.UAT_JOB_TIMEOUT_MS ?? 120_000);
  let observed: Document | undefined;
  let jobs: unknown;
  while (Date.now() < deadline) {
    observed = await api.document(id);
    jobs = await api.jobs(id);
    if (predicate(observed)) return observed;
    if ((jobs as Array<{ status: string }>).some((job) => job.status === "failed")) break;
    await new Promise((resolve) => setTimeout(resolve, 750));
  }
  throw new Error(`Expected: ${expected}\nObserved: ${JSON.stringify(observed)}\nPending/failed jobs: ${JSON.stringify(jobs)}`);
}
