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
export async function git(cwd: string, args: string[], env?: Record<string, string>): Promise<string> {
  const { stdout } = await exec("git", args, {
    cwd,
    maxBuffer: 16 * 1024 * 1024,
    timeout: 60_000,   // a hung git call must not hang the agent's tool call forever
    env: env ? { ...process.env, ...env } : undefined,
  });
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
  if (!r.ok) {
    const body = await r.text().catch(() => "");
    throw new Error(`gitly API ${path} -> HTTP ${r.status}${body ? `: ${body.slice(0, 300)}` : ""}`);
  }
  return r.json();
}
const post = (path: string, body: unknown) =>
  api(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

export const scanSecrets = (text: string) => post("/copilot/scan", { text });
export const analyzeDiff = (diff: string) => post("/lens/analyze", { diff });
export const traceSummary = (repo: string) => api(`/trace/summary?repo=${encodeURIComponent(repo)}`);
export const shrinkPlan = (diff: string, strength = "balanced") => post("/shrink/analyze", { diff, strength });

// ---- the gitly CLI (for tools whose logic lives in python: split, init) ----
export async function gitlyCli(cwd: string, args: string[]): Promise<string> {
  try {
    const { stdout, stderr } = await exec("gitly", args, { cwd, timeout: 300_000, maxBuffer: 16 * 1024 * 1024 });
    return (stdout + (stderr ? `\n${stderr}` : "")).trim();
  } catch (e: any) {
    if (e?.code === "ENOENT") {
      throw new Error("the `gitly` CLI isn't installed — run `pip install gitly` (or `pip install -e .` in the gitly repo).");
    }
    // the CLI's refusals (protected branch, secrets) arrive as nonzero exits — surface them verbatim
    throw new Error((e?.stderr || e?.stdout || e?.message || String(e)).trim());
  }
}

// ---- provenance ledger ----
export async function recordAuthorship(
  root: string,
  ev: { file_path: string; line_start: number; line_end: number; proposed_text?: string; model?: string; agent?: string; prompt?: string; session_id?: string },
  ledger = ".gitly/provenance",
): Promise<string> {
  const dir = join(root, ledger);
  await mkdir(dir, { recursive: true });
  const event_id = sha(`${ev.file_path}:${ev.line_start}:${Date.now()}:${Math.random()}`).slice(0, 32);
  // repo-relative paths, like the python SDK — they survive machine moves and feed `git show`
  const rel = ev.file_path.startsWith(root + "/") ? ev.file_path.slice(root.length + 1) : ev.file_path;
  const rec = {
    event_id,
    repo: root.split("/").filter(Boolean).pop() || "repo",
    file_path: rel,
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
    created_at: new Date().toISOString(),   // full ISO with Z — never a naive timestamp
  };
  await appendFile(join(dir, `${new Date().toISOString().slice(0, 10)}.jsonl`), JSON.stringify(rec) + "\n", "utf8");
  return event_id;
}

// ---- absorb: fold working changes into the right earlier commit(s) + re-stack ----
async function earliestOf(cwd: string, shas: string[]): Promise<string> {
  const order = (await git(cwd, ["log", "--format=%H", "-n", "300"])).split("\n").map((s) => s.trim());
  let best = shas[0], bestIdx = -1;
  for (const s of shas) {
    const i = order.indexOf(s);
    if (i > bestIdx) { bestIdx = i; best = s; }  // larger index = older commit
  }
  return best;
}

export async function absorb(cwd: string, into?: string): Promise<string> {
  if (!(await git(cwd, ["status", "--porcelain"])).trim()) return "Nothing to absorb — the working tree is clean.";
  const branch = await currentBranch(cwd);
  if (PROTECTED.test(branch)) return `Refusing to absorb on protected branch '${branch}'. Switch to a feature branch first.`;

  const changed = (await git(cwd, ["diff", "HEAD", "--name-only"])).split("\n").map((s) => s.trim()).filter(Boolean);
  if (!changed.length) return "Only new/untracked files to commit — nothing to absorb. Use gitly_safe_commit.";

  const upstream = (await git(cwd, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]).catch(() => "")).trim();
  const since = upstream ? `${upstream}..HEAD` : "";

  // Each changed file -> the last local commit that touched it (or an explicit `into`).
  const targets: Record<string, string[]> = {};
  for (const f of changed) {
    let target = into || "";
    if (!target) {
      const args = ["log", "-n", "1", "--format=%H"];
      if (since) args.push(since);
      args.push("--", f);
      target = (await git(cwd, args)).trim();
    }
    if (!target) return `No local commit found that touches "${f}". Commit it first (gitly_safe_commit) or pass \`into\`.`;
    (targets[target] ||= []).push(f);
  }

  // Never rewrite published history.
  if (upstream) {
    for (const t of Object.keys(targets)) {
      if ((await git(cwd, ["branch", "-r", "--contains", t]).catch(() => "")).trim()) {
        return `Target ${t.slice(0, 8)} is already pushed — refusing to rewrite published history.`;
      }
    }
  }

  // One fixup commit per target (stage only that target's files).
  for (const [t, fs] of Object.entries(targets)) {
    await git(cwd, ["reset", "-q"]);
    await git(cwd, ["add", "--", ...fs]);
    await git(cwd, ["commit", "-q", "--fixup", t]);
  }

  // Non-interactive autosquash rebase from just before the earliest target.
  const earliest = await earliestOf(cwd, Object.keys(targets));
  const hasParent = await git(cwd, ["rev-parse", "--verify", `${earliest}^`]).then(() => true).catch(() => false);
  const base = hasParent ? [`${earliest}^`] : ["--root"];
  try {
    await git(cwd, ["rebase", "-i", "--autosquash", ...base], { GIT_SEQUENCE_EDITOR: "true", GIT_EDITOR: "true" });
  } catch {
    await git(cwd, ["rebase", "--abort"]).catch(() => {});
    return "Could not absorb cleanly (rebase conflict). Aborted — your commits and changes are untouched.";
  }
  const nFiles = Object.values(targets).reduce((a, b) => a + b.length, 0);
  const tlist = Object.keys(targets).map((t) => t.slice(0, 8)).join(", ");
  return `Absorbed ${nFiles} file change(s) into ${Object.keys(targets).length} commit(s): ${tlist}. History re-stacked.`;
}
