import type { FullConfig, FullResult, Reporter, TestCase, TestResult } from "@playwright/test/reporter";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

type Finding = { id: string; name: string; status: string; classification: string; severity: string; confidence: string; error?: string; artifacts: string[] };
const severityFor = (id: string) => ["UAT-001", "UAT-002", "UAT-010", "UAT-020", "UAT-021", "UAT-030", "UAT-050"].includes(id) ? "critical" : "high";
function classification(error = "") {
  if (/No CSRF|ECONNREFUSED|net::ERR|shared libraries|browserType\.launch|UAT credentials rejected|Expected:.*Pending\/failed jobs/.test(error)) return "ENVIRONMENT_FAILURE";
  if (/Timeout.*locator|strict mode violation/.test(error)) return "TEST_DEFECT";
  return "APPLICATION_DEFECT";
}
function uatIds(title: string) { return title.match(/UAT-\d{3}/g) ?? ["UAT-UNKNOWN"]; }
function gh(command: string[]) { try { return execFileSync("gh", command, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim(); } catch { return null; } }

export default class UatReporter implements Reporter {
  private findings: Finding[] = []; private runId = process.env.UAT_RUN_ID ?? new Date().toISOString().replace(/[:.]/g, "-");
  onBegin(_config: FullConfig) { console.log(`lesspaper-ngl UAT run ${this.runId}`); }
  onTestEnd(test: TestCase, result: TestResult) {
    const failed = result.status === "failed";
    for (const id of uatIds(test.title)) this.findings.push({ id, name: test.title, status: failed ? "FAIL" : result.status === "skipped" ? "SKIPPED" : "PASS", classification: failed ? classification(result.error?.message) : result.status === "skipped" ? "EXPECTED_SKIP" : "", severity: severityFor(id), confidence: failed ? "medium" : "", error: result.error?.message, artifacts: result.attachments.map((a) => a.path).filter(Boolean) as string[] });
  }
  async onEnd(result: FullResult) {
    const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "uat", "reports", this.runId); await mkdir(root, { recursive: true });
    const failed = this.findings.filter((f) => f.status === "FAIL");
    const defects = failed.filter((f) => f.classification === "APPLICATION_DEFECT");
    const recommendation = defects.some((f) => f.severity === "critical" || f.severity === "blocker") ? "HOLD" : failed.length ? "REVIEW" : "PASS";
    const mode = process.env.UAT_ISSUES ?? "draft";
    const data = { runId: this.runId, origin: process.env.UAT_ORIGIN ?? "http://localhost:9398", outcome: result.status, findings: this.findings, counts: { pass: this.findings.filter(f => f.status === "PASS").length, fail: failed.length, skipped: this.findings.filter(f => f.status === "SKIPPED").length, applicationDefects: defects.length }, releaseRecommendation: recommendation };
    await writeFile(path.join(root, "summary.json"), JSON.stringify(data, null, 2));
    const lines = ["# lesspaper-ngl UAT", "", `Run: ${this.runId}`, `Origin: ${data.origin}`, "", "| UAT | Result | Classification | Severity |", "| --- | --- | --- | --- |", ...this.findings.map((f) => `| ${f.id} | ${f.status} | ${f.classification || "—"} | ${f.severity} |`), "", `## Release recommendation: ${recommendation}`];
    await writeFile(path.join(root, "summary.md"), `${lines.join("\n")}\n`);
    if (mode !== "off") for (const finding of defects) {
      const body = `## Area\n\n${finding.name.split("—")[0].trim()}\n\n## UAT\n\n${finding.id} — ${finding.name}\n\n## Summary\n\nDeterministic UAT failed.\n\n## Actual\n\n\`\`\`\n${finding.error ?? "No error supplied"}\n\`\`\`\n\n## Failure classification\n\nAPPLICATION_DEFECT\n\n## Automated analysis\n\nLikely failure boundary is represented by the failed deterministic assertion. Root cause is unverified.\n\nConfidence: ${finding.confidence}\n`;
      const draft = path.join(root, `${finding.id}-issue.md`); await writeFile(draft, body);
      if (mode === "auto" && ["blocker", "critical", "high"].includes(finding.severity) && gh(["auth", "status"])) {
        const duplicates = gh(["search", "issues", "--state", "open", "--search", finding.id, "--json", "number", "--jq", ".[].number"]);
        if (!duplicates) gh(["issue", "create", "--title", `[UAT] ${finding.name}`, "--body-file", draft]);
      }
    }
    console.log(`UAT: ${data.counts.pass} PASS, ${data.counts.fail} FAIL, ${data.counts.skipped} SKIPPED — ${recommendation}`);
  }
}
