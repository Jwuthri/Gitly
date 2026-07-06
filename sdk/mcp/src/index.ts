#!/usr/bin/env node
// gitly MCP server — drive gitly from inside Claude Code / Cursor / Windsurf.
// Composes local git + the gitly backend API + the provenance ledger into opinionated tools.
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { existsSync } from "node:fs";
import * as g from "./lib.js";

const TOOLS: any[] = [
  {
    name: "gitly_status",
    description: "Git status + change size with reviewability guidance (≤200 lines ideal, >400 hard to review) and a protected-branch warning.",
    inputSchema: { type: "object", properties: { cwd: { type: "string", description: "repo path (default: server cwd)" } } },
  },
  {
    name: "gitly_scan_secrets",
    description: "Scan text or the staged diff for secrets via the gitly secret firewall. Returns findings + a redacted preview. Run BEFORE committing.",
    inputSchema: { type: "object", properties: { text: { type: "string" }, staged: { type: "boolean", description: "scan `git diff --cached` instead of `text`" }, cwd: { type: "string" } } },
  },
  {
    name: "gitly_explain_diff",
    description: "Explain a diff as conceptual changes (gitly lens). Pass `diff`, or set `staged`/`base` to read it from git.",
    inputSchema: { type: "object", properties: { diff: { type: "string" }, staged: { type: "boolean" }, base: { type: "string", description: "diff base...HEAD" }, cwd: { type: "string" } } },
  },
  {
    name: "gitly_safe_commit",
    description: "Commit cleanly: stage changes, BLOCK if the staged diff contains secrets, refuse on protected branches, otherwise commit with `message`. The anti-`git add . && commit -m wip` tool.",
    inputSchema: { type: "object", properties: { message: { type: "string" }, all: { type: "boolean", description: "stage all incl. untracked (git add -A); default stages tracked changes (git add -u)" }, cwd: { type: "string" } }, required: ["message"] },
  },
  {
    name: "gitly_trace_summary",
    description: "AI-authorship provenance rollup for a repo: % AI vs human, by model, and unreviewed-AI lines.",
    inputSchema: { type: "object", properties: { repo: { type: "string", description: "repo name (default: current repo)" }, cwd: { type: "string" } } },
  },
  {
    name: "gitly_record_authorship",
    description: "Record that an AI wrote a span of code (feeds `gitly trace`). The prompt is secret-redacted before it is stored.",
    inputSchema: { type: "object", properties: { file_path: { type: "string" }, line_start: { type: "number" }, line_end: { type: "number" }, model: { type: "string" }, agent: { type: "string" }, prompt: { type: "string" }, proposed_text: { type: "string" }, cwd: { type: "string" } }, required: ["file_path", "line_start", "line_end"] },
  },
  {
    name: "gitly_shrink",
    description: "Plan splitting a large change into a stack of small, dependency-ordered sub-PRs (gitly shrink). Reads the diff from git (base...HEAD) and returns the slice plan; materialization runs via the gitly CLI.",
    inputSchema: { type: "object", properties: { base: { type: "string", description: "base ref (default main)" }, strength: { type: "string", description: "gentle | balanced | aggressive" }, cwd: { type: "string" } } },
  },
  {
    name: "gitly_split",
    description: "Split the working tree into several logical commits, one per concern (gitly commit --split): deps/config first, then source, tests, docs. Skips risky files, blocks secrets, refuses protected branches. Needs the gitly CLI installed.",
    inputSchema: { type: "object", properties: { all: { type: "boolean", description: "also include untracked files" }, cwd: { type: "string" } } },
  },
  {
    name: "gitly_init",
    description: "Install gitly's git hooks in this repo: the secret-blocking pre-commit hook and the post-commit hook that binds AI-authorship events (feeds gitly_trace_summary). Needs the gitly CLI installed.",
    inputSchema: { type: "object", properties: { claude_code: { type: "boolean", description: "also register the Claude Code authorship-capture hook in .claude/settings.json" }, cwd: { type: "string" } } },
  },
  {
    name: "gitly_absorb",
    description: "Fold uncommitted working changes into the right earlier commit(s) and re-stack (Sapling-style absorb). Each changed file goes into the last local commit that touched it, unless `into` targets one commit. Refuses on protected branches or already-pushed commits; aborts cleanly on conflict.",
    inputSchema: { type: "object", properties: { into: { type: "string", description: "optional: a commit ref to absorb every change into" }, cwd: { type: "string" } } },
  },
];

async function dispatch(name: string, a: any, cwd: string): Promise<string> {
  switch (name) {
    case "gitly_status": {
      const branch = await g.currentBranch(cwd);
      const numstat = await g.git(cwd, ["diff", "--numstat"]).catch(() => "");
      const lines = numstat.trim().split("\n").filter(Boolean).reduce((s, l) => {
        const [add, del] = l.split("\t");
        return s + (parseInt(add) || 0) + (parseInt(del) || 0);
      }, 0);
      const verdict = lines === 0 ? "no unstaged changes"
        : lines <= 200 ? "ideal review size"
        : lines <= 400 ? "getting large — consider splitting"
        : "too large to review well — split with gitly_shrink";
      const warn = g.PROTECTED.test(branch) ? `\n[!] on protected branch '${branch}' — create a feature branch before committing.` : "";
      const status = (await g.git(cwd, ["status", "--short"]).catch(() => "")).trim();
      return `branch: ${branch || "(none)"}\nunstaged: ${lines} changed lines — ${verdict}${warn}\n\n${status || "(working tree clean)"}`;
    }
    case "gitly_scan_secrets": {
      const text = a.staged ? await g.git(cwd, ["diff", "--cached"]) : (a.text || "");
      if (!text.trim()) return "Nothing to scan (pass `text` or set `staged: true`).";
      const r = await g.scanSecrets(text);
      if (r.clean) return "✓ No secrets detected — safe to commit.";
      const list = r.findings.map((f: any) => `  • ${f.kind} (line ${f.line})`).join("\n");
      return `✗ ${r.findings.length} potential secret(s) — DO NOT COMMIT:\n${list}\n\nRedacted preview:\n${r.redacted_preview ?? ""}`;
    }
    case "gitly_explain_diff": {
      let diff = a.diff || "";
      if (!diff) {
        diff = a.staged ? await g.git(cwd, ["diff", "--cached"])
          : a.base ? await g.git(cwd, ["diff", `${a.base}...HEAD`])
          : await g.git(cwd, ["diff"]);
      }
      if (!diff.trim()) return "No diff to explain.";
      const r = await g.analyzeDiff(diff);
      const lines = (r.clusters || [])
        .map((c: any) =>
          `  • [${c.confidence}] ${c.title} (${c.site_count} sites/${c.file_count} files)` +
          (c.outliers?.length ? `  ! ${c.outliers.length} outlier(s)` : ""))
        .join("\n");
      return `${r.stats.files_changed} file(s), +${r.stats.lines_added}/-${r.stats.lines_removed}, ${r.stats.cluster_count} cluster(s):\n${lines}`;
    }
    case "gitly_safe_commit": {
      const branch = await g.currentBranch(cwd);
      if (g.PROTECTED.test(branch)) return `Refusing to commit to protected branch '${branch}'. Create a feature branch first.`;
      await g.git(cwd, ["add", a.all ? "-A" : "-u"]);
      const staged = await g.git(cwd, ["diff", "--cached"]);
      if (!staged.trim()) return "Nothing staged to commit.";
      const scan = await g.scanSecrets(staged);
      if (!scan.clean) {
        await g.git(cwd, ["reset"]).catch(() => {});
        const list = scan.findings.map((f: any) => `  • ${f.kind} (line ${f.line})`).join("\n");
        return `✗ Commit BLOCKED — staged changes contain secrets:\n${list}\n(changes unstaged) Remove the secrets and try again.`;
      }
      await g.git(cwd, ["commit", "-m", a.message]);
      const head = (await g.git(cwd, ["rev-parse", "--short", "HEAD"])).trim();
      return `✓ Committed ${head} on ${branch}: ${a.message}`;
    }
    case "gitly_trace_summary": {
      const repo = a.repo || await g.repoName(cwd);
      const s = await g.traceSummary(repo);
      const pct = s.total_lines ? Math.round((100 * s.ai_lines) / s.total_lines) : 0;
      const models = Object.entries(s.by_model || {}).map(([k, v]) => `${k}=${v}`).join(", ") || "—";
      return `repo: ${repo}\nlines ${s.total_lines} | AI ${pct}% (${s.ai_lines}) · human ${s.human_lines} · hybrid ${s.hybrid_lines}\nunreviewed AI lines: ${s.unreviewed_ai_lines}\nby model: ${models}`;
    }
    case "gitly_record_authorship": {
      const root = await g.repoRoot(cwd);
      const id = await g.recordAuthorship(root, a);
      return `recorded authorship ${id} for ${a.file_path}:${a.line_start}-${a.line_end} (${a.model || "ai"})`;
    }
    case "gitly_shrink": {
      const base = a.base || "main";
      const diff = await g.git(cwd, ["diff", `${base}...HEAD`]).catch(async () =>
        g.git(cwd, ["diff", "master...HEAD"]));   // repos whose trunk is master
      if (!diff.trim()) return `No diff between ${base} and HEAD — nothing to shrink.`;
      const r = await g.shrinkPlan(diff, a.strength || "balanced");
      const rows = (r.slices || []).map((s: any) =>
        `  #${s.order} ${s.title} — ${s.lines} lines / ${s.files} file(s)` +
        (s.depends_on?.length ? `  (after #${s.depends_on.join(", #")})` : "")).join("\n");
      return `${r.original_lines} lines across ${r.original_files} file(s) → ${r.slices?.length ?? 0} slice(s) [${r.strength}]:\n${rows}\n\n${r.note || ""}`;
    }
    case "gitly_split":
      return await g.gitlyCli(cwd, ["commit", "--split", ...(a.all ? ["-a"] : [])]);
    case "gitly_init":
      return await g.gitlyCli(cwd, ["init", ...(a.claude_code ? ["--claude-code"] : [])]);
    case "gitly_absorb":
      return await g.absorb(cwd, a.into);
    default:
      return `unknown tool: ${name}`;
  }
}

const server = new Server({ name: "gitly", version: "0.0.1" }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));
server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const a: any = req.params.arguments ?? {};
  const cwd = (a.cwd as string) || process.cwd();
  if (!existsSync(cwd)) {
    return { content: [{ type: "text", text: `gitly error: cwd does not exist: ${cwd}` }], isError: true };
  }
  try {
    return { content: [{ type: "text", text: await dispatch(req.params.name, a, cwd) }] };
  } catch (e: any) {
    return { content: [{ type: "text", text: `gitly error: ${e?.message || String(e)}` }], isError: true };
  }
});

await server.connect(new StdioServerTransport());
console.error(`gitly MCP server running on stdio (API: ${g.API})`);
