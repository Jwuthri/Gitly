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

The interactive analyzer lives on the web UI at **`/lens`**, wired to the backend:

```bash
curl -s localhost:8000/lens/analyze \
  -H 'content-type: application/json' \
  -d '{"diff": "<unified diff>"}'
```

The response is the file/hunk skeleton plus the clusters (kind, title, confidence, the
sites each one covers).

!!! note "CLI status"
    `gitly lens <file.diff>` is currently a stub that points at the migration notes — the
    **engine itself is live** behind the HTTP API and inside the commit-message heuristic.
    The standalone CLI subcommand is on the roadmap.

## Lineage

`lens` is the consolidation of the `pr-visual-diff` project into gitly, rebuilt on the
shared `diff_core` kernel. It uses its own lenient diff parser tuned for messy,
real-world diffs (more forgiving than the strict parser `shrink` relies on).
