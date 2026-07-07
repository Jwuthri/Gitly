# Trace — AI authorship provenance

> `git blame` tells you who *typed* it. `gitly trace` tells you who — or what — actually
> *wrote* it.

As more code is written by agents, "who wrote this?" stops meaning "who typed it." `trace`
is git-native AI-authorship provenance: a record of **which model or agent wrote which
line, from which prompt, how much a human changed it, and whether it's been reviewed** —
surfaced as a blame-style CLI and a web dashboard.

## The CLI

=== "Per-line"

    ```console
    $ gitly trace app/api.py
        1  human                       import os
        2  AI:claude-sonnet-4 !unreviewed   def rate_limit(request):
        3  AI:claude-sonnet-4~          return _check(request)
    ```

    Each line is tagged:

    - `human` — written by a person.
    - `AI:<model>` — written by a model/agent. A trailing `~` means **inferred** (not
      explicitly recorded), and `!unreviewed` flags AI lines a human hasn't signed off on.

    Review is cleared by any of three signals — no manual bookkeeping required:

    1. **GitHub PR approvals** — `gitly review --from-github` (run it in CI after merges)
       marks every commit of an approved, merged PR as reviewed via the `gh` CLI.
    2. **`Reviewed-by:` / `Acked-by:` trailers** — honored automatically at trace time.
    3. **Explicit** — `gitly review <file>` / `--commit <sha>` / `--all` for everything else.

=== "Repo summary"

    ```console
    $ gitly trace --summary
    repo: my-app
    lines: 4120   ai: 2890 (70%)   human: 1100   hybrid: 130
    unreviewed AI lines: 410
    by model: claude-sonnet-4=2100, gpt-4o=790
    ```

## How provenance is captured

```
agent edit → capture hook → redacted event → local ledger
   → (post-commit) bind to commit → record  → (opt-in) Postgres → trace
```

1. An agent edits a file (e.g. via Claude Code or the MCP server).
2. A **`PostToolUse` capture hook** records the authorship **event** (model, agent, redacted prompt).
3. The event is written to a local ledger at `.gitly/provenance/*.jsonl`.
4. **At commit time**, the **`post-commit` hook** runs **`gitly bind`** (installed by `gitly init`):
   it consumes each pending event, compares the AI's proposed text against what was actually
   committed, and writes a commit-bound **record** with a **`human_edit_ratio`**. A span a human
   changed by ≥ 50 % is reclassified **`hybrid`**. A `.bound` cursor guarantees no event is bound twice.
5. `gitly trace` **joins records (then events) with `git blame`** — so it shows real edit ratios
   and hybrid lines *offline*, no database required.
6. Optionally (`GITLY_PROVENANCE_SYNC=true`) records sync to Postgres for the dashboard;
   the server **re-redacts** prompts on ingest as a second gate.

> 🔧 **`gitly bind`** runs automatically via the hook, but you can run it by hand anytime.
> A `hybrid` line then renders like `hybrid:claude-sonnet-4-6 (62% human)`.

!!! shield "Prompts never carry secrets"
    Provenance records store the prompt that produced the code. That prompt is redacted
    **before it touches disk** and again **on server ingest** — see [Security](../security.md).

## The dashboard

The web UI at **`/trace`** turns the ledger into:

- stat cards (% AI, human, hybrid; unreviewed-AI count),
- an authorship bar and per-model breakdown,
- a **file tree** you can click into, and a **git-blame-style view** showing per-line
  authorship for the selected file.

Seed realistic demo data to explore it:

```bash
make seed                                # idempotent; posts via the real ingest path
# then open http://localhost:3000/trace?repo=demo-app
```

## Recording from code

The dependency-free `gitly_sdk` (in `sdk/python/`) lets a tool record authorship directly;
the MCP tool `gitly_record_authorship` does the same from inside an agent. Both write the
same redacted ledger that `gitly trace` reads.
