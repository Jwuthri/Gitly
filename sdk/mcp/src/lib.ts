// Shared helpers for the gitly MCP server: local git, the gitly backend API, and the
// provenance ledger (a TS mirror of gitly-sdk so the server is pure Node).
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { appendFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { createHash } from "node:crypto";

const exec = promisify(execFile);
export const API = process.env.GITLY_API_URL || "http://localhost:8000";

// ---- git ----
export async function git(cwd: string, args: string[]): Promise<string> {
  const { stdout } = await exec("git", args, { cwd, maxBuffer: 16 * 1024 * 1024 });
  return stdout;
}
export async function repoRoot(cwd: string): Promise<string> {
  try { return (await git(cwd, ["rev-parse", "--show-toplevel"])).trim(); } catch { return cwd; }
}
export async function repoName(cwd: string): Promise<string> {
  return (await repoRoot(cwd)).split("/").filter(Boolean).pop() || "repo";
}
export async function currentBranch(cwd: string): Promise<string> {
  try { return (await git(cwd, ["rev-parse", "--abbrev-ref", "HEAD"])).trim(); } catch { return ""; }
}
export const PROTECTED = /^(main|master|develop|release)$/;

// ---- secret redaction (mirror of backend/sdk) ----
const PATTERNS: [string, RegExp][] = [
  ["aws_access_key_id", /AKIA[0-9A-Z]{16}/g],
  ["github_token", /gh[pousr]_[A-Za-z0-9]{36,}/g],
  ["anthropic_key", /sk-ant-[A-Za-z0-9_-]{20,}/g],
  ["openai_key", /sk-[A-Za-z0-9]{20,}/g],
  ["private_key", /-----BEGIN [A-Z ]*PRIVATE KEY-----/g],
  ["jwt", /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g],
  ["generic", /(?:api[_-]?key|secret|token|password)\s*[:=]\s*['"][^'"]{12,}['"]/gi],
];
export function redact(text: string): string {
  let out = text || "";
  for (const [kind, re] of PATTERNS) out = out.replace(re, `‹redacted:${kind}›`);
  return out;
}
const sha = (s: string) => createHash("sha256").update(s || "").digest("hex");

// ---- backend api ----
async function api(path: string, init?: RequestInit): Promise<any> {
  const r = await fetch(`${API}${path}`, init);
  if (!r.ok) throw new Error(`gitly API ${path} -> HTTP ${r.status}`);
  return r.json();
}
const post = (path: string, body: unknown) =>
  api(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

export const scanSecrets = (text: string) => post("/copilot/scan", { text });
export const analyzeDiff = (diff: string) => post("/lens/analyze", { diff });
export const traceSummary = (repo: string) => api(`/trace/summary?repo=${encodeURIComponent(repo)}`);
export const shrinkJob = (repo: string, base: string, head: string) => post("/shrink/jobs", { repo, base, head });

// ---- provenance ledger ----
export async function recordAuthorship(
  root: string,
  ev: { file_path: string; line_start: number; line_end: number; proposed_text?: string; model?: string; agent?: string; prompt?: string; session_id?: string },
  ledger = ".gitly/provenance",
): Promise<string> {
  const dir = join(root, ledger);
  await mkdir(dir, { recursive: true });
  const event_id = sha(`${ev.file_path}:${ev.line_start}:${Date.now()}:${Math.random()}`).slice(0, 32);
  const rec = {
    event_id,
    repo: root.split("/").filter(Boolean).pop() || "repo",
    file_path: ev.file_path,
    content_hash: sha(ev.proposed_text || ""),
    line_start: ev.line_start,
    line_end: ev.line_end,
    author_type: "ai",
    model: ev.model ?? null,
    agent: ev.agent ?? "unknown",
    session_id: ev.session_id ?? null,
    prompt_ref: ev.prompt ? sha(ev.prompt).slice(0, 16) : null,
    prompt_redacted: ev.prompt ? redact(ev.prompt) : null,
    proposed_text: redact(ev.proposed_text || ""),
    created_at: new Date().toISOString().slice(0, 19),
  };
  await appendFile(join(dir, `${new Date().toISOString().slice(0, 10)}.jsonl`), JSON.stringify(rec) + "\n", "utf8");
  return event_id;
}
