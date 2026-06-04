# Security

gitly's first rule is a hard one:

!!! danger "gitly must never become the leak"
    No secret is ever committed, persisted, or sent to an LLM — not even to your own agent.
    This is a non-negotiable design constraint, enforced in code, not a best-effort hope.

## Local-first

Everything core runs on your machine. The CLI talks to local git; the brain prefers your
local Claude Code CLI; provenance is written to a local ledger. The server, the database,
and any LLM call are all **opt-in**.

## The secret firewall

A layered detector combining high-recall regex patterns (AWS, GitHub, OpenAI, Anthropic,
Google, Slack, JWTs, private keys, generic `key = "..."` assignments) with a **Shannon
entropy** check to catch high-entropy blobs the patterns miss. No single scanner is
sufficient, so gitly combines approaches and **fails closed**.

It runs at **three gates**:

```
agent (MCP / CLI)  →  pre-commit hook  →  pre-push hook
```

…and a fourth, quieter role: **redaction**. Before any prompt or diff is sent to a model
or written to disk, `redact()` replaces each detected secret with a typed placeholder like
`‹redacted:openai_key›`.

### Allowlisting false positives

Test fixtures and docs sometimes need to contain example secrets. Mark such a line with a
pragma — `# gitly:allow` (or the de-facto-standard `# pragma: allowlist secret`) — and the
**commit gate** skips it:

```python
FAKE_AWS_KEY = "AKIA................"  # gitly:allow
```

!!! warning "Redaction ignores the pragma"
    The allowlist exempts a line from *blocking a commit* — it does **not** exempt it from
    redaction. A pragma'd line is still stripped before any LLM call or on-disk prompt, so
    an allowlist can never become a leak path.

## Where redaction happens

| Moment | Guard |
|---|---|
| `gitly commit` / `--split` | Staged diff scanned; commit **blocked** on any finding. |
| Any brain call (commit msg, splitting, shrink labels) | Prompt+diff **redacted** before it leaves the machine. |
| Writing a provenance record | Prompt redacted **before it touches disk**. |
| `POST /trace/records` ingest | Prompts **re-redacted** server-side as a second gate. |

## The safe-add guard

Separate from secret *content*, gitly refuses to *stage* files that shouldn't be in git at
all: `.env` / `.env.*`, `*.pem` / `*.key` / `*.p12` / credentials, and build/vendor
artifacts (`node_modules/`, `dist/`, `.next/`, …). It also honors your `.gitignore`. Even
if you force a flagged file with `--path`, the secret firewall still inspects the staged
diff. Details: [Copilot → the safe-add guard](pillars/copilot.md#the-safe-add-guard).

## Key handling

- API keys are read from the environment or your project's `.env` — and gitly's loader
  uses `setdefault`, so it **never overrides** a real environment variable.
- Keys stored via `gitly auth` live at `~/.config/gitly/config.json` with **`chmod 600`**.
- `gitly config` shows only the **source** of a key, never its value.
- A key sent to a provider goes **only** to that provider's API over HTTPS.

## History safety

- `gitly commit` / `absorb` **refuse protected branches** (`main`/`master`/`develop`/`release`).
- `gitly absorb` **never rewrites pushed history** — if a target commit is already on the
  remote, it stops rather than force-rewriting published commits.

!!! note "On platform protections"
    GitHub branch protection does **not** block force-pushes by default, and push-protection
    isn't guaranteed to be on. gitly's hooks deliberately don't assume the platform will
    catch a leak — they catch it locally, first.
