# MCP server & Claude Code plugin

gitly meets you inside your AI agent. The same engines you run from the terminal are
exposed as an **MCP server** (for Claude Code, Cursor, and any MCP client) and bundled,
together with slash commands and a capture hook, as a one-install **Claude Code plugin**.

## The MCP server

A pure-Node **stdio** server (in `sdk/mcp/`) that composes local git + the gitly backend +
the provenance ledger into ten opinionated tools:

| Tool | Does |
|---|---|
| `gitly_status` | Working-tree / branch status, gitly-style. |
| `gitly_scan_secrets` | Run the secret firewall over text or staged changes. |
| `gitly_explain_diff` | Cluster a diff into conceptual cards (the lens engine). |
| `gitly_safe_commit` | Safe-staged, secret-checked, conventional commit. |
| `gitly_split` | Split the working tree into logical commits (`gitly commit --split`; needs the CLI). |
| `gitly_absorb` | Fold working changes into the right earlier commit(s). |
| `gitly_init` | Install gitly's git hooks (`gitly init`; needs the CLI). |
| `gitly_trace_summary` | Authorship rollup for the repo. |
| `gitly_record_authorship` | Write a (redacted) provenance record to the ledger. |
| `gitly_shrink` | Plan a shrink stack from `base...HEAD`. |

Point the server at a non-default backend with `GITLY_API_URL`.

??? example "Manual MCP config (without the plugin)"
    Add to your client's MCP config (Claude Code's `~/.claude.json`, Cursor's settings, …):

    ```json
    {
      "mcpServers": {
        "gitly": {
          "command": "node",
          "args": ["/path/to/Gitly/sdk/mcp/dist/index.js"],
          "env": { "GITLY_API_URL": "http://localhost:8000" }
        }
      }
    }
    ```

    Build it first: `cd sdk/mcp && npm install && npm run build`.

Once connected, just ask:

> *"gitly, is this change too big?"* · *"commit this cleanly with gitly"* ·
> *"gitly trace summary"*

## The Claude Code plugin

The repo root is also a **Claude Code plugin** (`.claude-plugin/plugin.json`) that bundles
everything in one install (`claude plugin validate` passes):

- **MCP server** — the 10 tools above, launched from `${CLAUDE_PLUGIN_ROOT}/sdk/mcp/dist`.
- **Slash commands** — `/commit`, `/absorb`, `/scan`, `/shrink`, `/lens`, `/trace`
  (in `commands/*.md`).
- **Hook** — a `PostToolUse(Edit|Write)` hook that records AI authorship to the local
  ledger, feeding `gitly trace`.

Load it for a session:

```bash
claude --plugin-dir /path/to/Gitly
```

Because the plugin uses `${CLAUDE_PLUGIN_ROOT}`, it resolves paths relative to wherever the
repo lives — no absolute paths to edit.
