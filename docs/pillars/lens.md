# Lens — read diffs

> Re-render a diff as conceptual **change clusters**, so review focuses on intent, not
> noise.

A 600-line diff that's really "one rename applied in 47 places" reads as 47 separate
changes in GitHub. `lens` clusters a diff into a handful of **conceptual cards** —
"this is one rename", "these three are the same insertion" — and flags the genuine
**outliers** that deserve a careful look.

## What it detects

The engine runs layered detectors over the parsed diff:

- **Token substitution** — the same identifier/symbol swapped consistently across many
  sites (a rename, an API replacement, a type change).
- **Insertion templates** — the same block inserted in several places (added logging,
  guards, decorators).
- **Outliers** — hunks that don't fit any cluster. These are where review attention
  belongs.

!!! abstract "Partition invariant"
    Every hunk lands in **exactly one** cluster — no hunk is double-counted, none is
    dropped. The clustering is a true partition of the diff, which is what makes the
    "N changes → M concepts" summary trustworthy.

Each cluster carries a **confidence** (`high` / `medium` / `low`), a site count, and a
human-readable title. gitly's commit-message heuristic reuses exactly this engine: a
high-confidence rename cluster becomes a `refactor:` message, for instance.

## Try it

From the terminal — point it at a diff file or pipe one in:

```console
$ git diff main | gitly lens --sites
lens analysis
  2 files  +2/-2  2 hunks  ->  1 clusters

  ● rename: Renamed `old_name` → `new_name`   [2 sites / 2 files]  (high)
      Same substitution at 2 sites across 2 files.
        · a.py:1
        · b.py:1
```

`--json` emits the raw `AnalysisResult`; `--sites` lists every occurrence. See the
[CLI reference](../reference/cli.md#gitly-lens).

The same engine powers the interactive analyzer on the web UI at **`/lens`** and the
HTTP API:

```bash
curl -s localhost:8000/lens/analyze \
  -H 'content-type: application/json' \
  -d '{"diff": "<unified diff>"}'
```

## Lineage

`lens` is the consolidation of the `pr-visual-diff` project into gitly, rebuilt on the
shared `diff_core` kernel. It uses its own lenient diff parser tuned for messy,
real-world diffs (more forgiving than the strict parser `shrink` relies on).
