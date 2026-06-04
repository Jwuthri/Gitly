# Git hooks

gitly ships two hooks — one to stop secrets at the git boundary, one to capture AI
authorship as your agent works.

## Quick install: `gitly init`

The easiest way — one command, from inside the repo:

```bash
gitly init                 # installs the secret-blocking pre-commit hook
gitly init --claude-code   # …and registers the Claude Code authorship-capture hook
```

It's idempotent, and won't clobber an existing non-gitly `pre-commit` hook without
`--force` (which backs the old one up). Prefer this over the manual steps below. See the
[CLI reference](../reference/cli.md#gitly-init).

## `pre-commit` — block secrets (manual)

Refuses a commit whose staged diff contains secrets, using the `gitly` CLI (with a small
regex fallback if the CLI isn't on `PATH`). This is the same firewall `gitly commit` uses,
but it also protects plain `git commit`.

```bash
ln -sf ../../sdk/hooks/pre-commit .git/hooks/pre-commit
```

Now any commit path is covered:

```console
$ git commit -m "wip"
  secret[openai_key] line 12: sk-proj-abc…
x 1 potential secret(s) — commit blocked.
```

You can also run the scan ad hoc:

```bash
gitly scan --staged        # exit 1 if the staged diff has secrets
echo "$SUSPECT" | gitly scan
```

## `claude_post_tool.py` — capture authorship

A Claude Code **`PostToolUse(Edit|Write)`** hook that records who wrote each change to the
local provenance ledger (feeds [`gitly trace`](../pillars/trace.md)). Prompts are redacted
before they're written.

Register it in `.claude/settings.json` (a ready-to-paste snippet is at the top of the hook
file):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "command": "python3 /path/to/Gitly/sdk/hooks/claude_post_tool.py" }
        ]
      }
    ]
  }
}
```

!!! tip
    If you install the [Claude Code plugin](mcp.md#the-claude-code-plugin), this hook is
    wired up for you — no manual `settings.json` edit needed.

## The three gates

Together with the agent-side MCP check, these hooks form gitly's defense in depth:

```
agent (MCP / CLI)  →  pre-commit hook  →  pre-push hook
```

No single secret scanner is perfect, and platform push-protection isn't guaranteed — so
gitly checks at every gate. More in [Security](../security.md).
