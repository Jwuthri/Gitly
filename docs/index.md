# gitly

**Git-quality tooling for the AI-authorship era.** gitly helps any developer — experienced or "vibe coding" — commit cleanly, ship reviewable PRs, understand diffs, and know who *really* wrote the code. It meets you where you already are: in your terminal and inside your AI coding agent.

!!! quote ""
    `git blame` tells you who *typed* it. **`gitly trace`** tells you who — or what — actually *wrote* it.

---

## The four pillars

```
        AUTHOR        →     STRUCTURE    →      REVIEW
       copilot              shrink              lens
          └──────────────────┬──────────────────┘
                          TRACE
        provenance ground-truth beneath all three
```

<div class="grid cards" markdown>

-   :material-source-commit: **Copilot — commit correctly**

    ---

    No more `git add . && git commit -m "wip"`. Safe staging that never grabs your
    `.env`, auto-written conventional messages, semantic `--split`, `absorb`, and a
    secret firewall — all backed by a zero-config "brain".

    [:octicons-arrow-right-24: Copilot](pillars/copilot.md)

-   :material-call-split: **Shrink — split big PRs**

    ---

    Turn an unreviewable megaPR into a dependency-ordered stack of small sub-PRs,
    with a **verified** completeness guarantee: `tree(base + slices) == tree(head)`.

    [:octicons-arrow-right-24: Shrink](pillars/shrink.md)

-   :material-magnify-scan: **Lens — read diffs**

    ---

    Re-render a diff as conceptual **change clusters** ("this 47-site rename is one
    thing") with outlier flagging, so review focuses on intent, not noise.

    [:octicons-arrow-right-24: Lens](pillars/lens.md)

-   :material-fingerprint: **Trace — AI provenance**

    ---

    Git-native AI authorship provenance. Records which model/agent wrote which line,
    from which (redacted) prompt, how much a human changed it, and whether it was
    reviewed.

    [:octicons-arrow-right-24: Trace](pillars/trace.md)

</div>

---

## Why gitly

People increasingly **vibe-code** with AI agents but never learned git. The result is
giant, unreviewable PRs, `wip` commit messages, accidentally committed secrets, and no
record of what the AI actually wrote. gitly fixes the *workflow*, not just the symptoms:

- **Local-first and safe by default.** Everything works offline. The secret firewall
  runs at three gates and **redacts before anything ever reaches an LLM** — gitly never
  becomes the leak.
- **Zero-config intelligence.** If you have Claude Code installed, `gitly commit` writes
  your messages with no API key at all. Otherwise drop a key in `.env` and you're done.
- **Verifiable, not vibes.** `shrink` proves its stack reconstructs your tree exactly;
  `lens` guarantees every hunk lands in exactly one cluster.
- **Meets you in your agent.** Ship as a terminal CLI **and** an MCP server + Claude Code
  plugin, so the same engines work from the shell or from inside Cursor / Claude Code.

---

## 60-second tour

```bash
pip install -e .          # the lean `gitly` CLI (no server deps)

gitly commit              # stage safe files, write a conventional message, commit
gitly commit --split      # carve a sprawling working tree into reviewable commits
gitly absorb              # fold edits into the earlier commit they belong to
gitly trace app.py        # per-line: who (or what) wrote each line
gitly shrink main HEAD    # split this branch into a verified stack of small PRs
```

[Get started :material-arrow-right:](getting-started/installation.md){ .md-button .md-button--primary }
[See the CLI reference :material-arrow-right:](reference/cli.md){ .md-button }

---

## Status

| Pillar | Status |
|---|---|
| **copilot** | `commit` · `absorb` · `--split` · `scan` **live** (CLI) |
| **shrink** | **live** — CLI + plan API, verified stacks |
| **lens** | **live** — substitution · insertion · outlier clustering |
| **trace** | **live** — recorder + blame-join CLI + dashboard |

The `shrink` and `lens` engines consolidate two sibling projects (`pr-shrinker`,
`pr-visual-diff`) into one toolchain on a single shared diff kernel.
