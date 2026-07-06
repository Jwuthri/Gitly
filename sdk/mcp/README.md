# @gitly/mcp

The **gitly MCP server** — how vibe coders reach gitly without leaving their AI agent.

It runs on your machine over stdio and *composes* three things into opinionated tools:
local **git**, the gitly **backend API** (`GITLY_API_URL`, default `http://localhost:8000`),
and the provenance **ledger**. It builds on the same ecosystem as the official
[GitHub MCP server](https://github.com/github/github-mcp-server) and first-party
[git MCP server](https://github.com/modelcontextprotocol/servers/tree/main/src/git) — but
adds the best-practices layer + the gitly engines on top.

## Tools

| Tool | What it does |
|---|---|
| `gitly_status` | Git status + change size with reviewability guidance (≤200 ideal, >400 too big) and a protected-branch warning. |
| `gitly_scan_secrets` | Scan text or the staged diff with the secret firewall; returns findings + a redacted preview. |
| `gitly_explain_diff` | Explain a diff as conceptual changes (lens) — pass `diff`, or read from `staged`/`base`. |
| `gitly_safe_commit` | Stage → **block on secrets** → refuse on protected branches → commit. The anti-`git add . && commit -m "wip"` tool. |
| `gitly_trace_summary` | AI-authorship rollup for a repo: % AI vs human, by model, unreviewed-AI lines. |
| `gitly_record_authorship` | Record that an AI wrote a span (feeds `gitly trace`); the prompt is secret-redacted first. |
| `gitly_shrink` | Plan splitting a large change into a dependency-ordered stack of small sub-PRs (reads `base...HEAD` from git). |
| `gitly_split` | Split the working tree into several logical commits, one per concern (`gitly commit --split`; needs the gitly CLI). |
| `gitly_absorb` | Fold working changes into the right earlier commit(s) and re-stack (Sapling-style). Refuses on protected/pushed history; aborts cleanly on conflict. |
| `gitly_init` | Install the secret pre-commit + bind post-commit hooks (`gitly init`; needs the gitly CLI). |

## Build & run

```bash
cd sdk/mcp
npm install
npm run build      # tsc -> dist/
npm run smoke      # optional: verify against a running backend (make up)
```

## Add to Claude Code

```bash
claude mcp add gitly -- node /absolute/path/to/gitly/sdk/mcp/dist/index.js
# point at a non-default backend:
#   claude mcp add gitly --env GITLY_API_URL=http://localhost:8000 -- node .../dist/index.js
```

Then, inside any repo:

> "gitly, is this change too big?" · "commit this cleanly with gitly" · "gitly, scan for secrets" · "gitly trace summary"

The differentiated value vs. a plain git MCP: **commit *correctly*, never leak a key, never
ship an unreviewable blob — and record who wrote it.**
