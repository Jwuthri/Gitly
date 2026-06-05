# Shrink — split big PRs

> Turn an unreviewable megaPR into a dependency-ordered stack of small sub-PRs — with a
> **verified** completeness guarantee.

Large PRs don't get reviewed; they get rubber-stamped. `shrink` takes a range
(`base..head`) and proposes a **stack of small slices**, each a coherent unit, ordered so
dependencies come first — then proves the stack reconstructs your tree *exactly*.

```bash
gitly shrink <base> [head] [OPTIONS]
```

```console
$ gitly shrink main HEAD --strength balanced
1320 lines / 18 files  ->  4 slices
  #1  chore: bump dependencies        [40 ln / 2 files]
  #2  feat: rate-limiter core         [220 ln / 5 files]  (after #1)
  #3  feat: wire limiter into API     [180 ln / 6 files]  (after #2)
  #4  test: cover the limiter         [90 ln / 5 files]   (after #2)
ok: completeness verified — tree(base + slices) == tree(head)
```

## How it works

```
parse  →  plan  →  materialize  →  verify
```

1. **Parse** the unified diff into files and hunks (on the shared `diff_core` kernel).
2. **Plan** — group hunks by category and module, infer dependencies, and compute a
   topological order with `networkx` so each slice only depends on earlier ones.
3. **Materialize** — build the commit stack with git plumbing (one commit per slice).
4. **Verify** — the crown jewel: gitly checks `tree(base + slices) == tree(head)` by exact
   **git tree-ID equality**. If the stack doesn't reproduce your head tree byte-for-byte,
   it is **not shipped**.

!!! success "Completeness is proven, not promised"
    The completeness check is a hard gate. A passing run means: apply these slices on
    `base`, in order, and you land on precisely `head` — nothing dropped, nothing extra.

## Strength

Tune how aggressively the branch is sliced:

| `--strength` | Max lines / slice | Min lines | Max slices |
|---|---|---|---|
| `gentle` | 1500 | 300 | 2 |
| `balanced` *(default)* | 400 | 40 | 6 |
| `aggressive` | 120 | 1 | 20 |

```bash
gitly shrink main HEAD --strength aggressive
gitly shrink main HEAD --max-lines 250        # override the line cap directly
```

## Options

| Flag | Meaning |
|---|---|
| `base` (positional, required) | Base ref, e.g. `main`. |
| `head` (positional) | Head ref (default `HEAD`). |
| `--strength` | `gentle` \| `balanced` \| `aggressive`. |
| `--max-lines N` | Override the per-slice line cap (`0` = use `--strength`). |
| `--write-refs` | Create `shrink/*` branches for each materialized slice. |
| `--pr` | Push the slices and open **chained stacked PRs** on GitHub. |
| `--remote` | Remote to push slice branches to (default `origin`). |
| `--llm` | Use the LLM labeler for slice titles/intent (redacted first). |
| `--repo PATH` | Path to the git repo. |

With `--write-refs`, gitly prints the created branch and commit for each slice so you can
push them as a stack.

## Ship it — stacked PRs

`--pr` takes the verified stack all the way to GitHub: it pushes each `shrink/*` branch and
opens **one PR per slice, chained** — slice 1 based on your real base, slice 2 based on
slice 1, and so on. That's a true stacked-PR set, each piece small and reviewable.

```console
$ gitly shrink main HEAD --pr
83 lines / 4 files  ->  3 slices
  #1  chore: dependencies   [2 ln / 1 files]
  #2  feat: core            [80 ln / 2 files]  (after #1)
  #3  test: cover           [1 ln / 1 files]   (after #2)
ok: completeness verified — tree(base + slices) == tree(head)
opening stacked PRs:
  ✓ shrink/1-dependencies → main
  ✓ shrink/2-core         → shrink/1-dependencies
  ✓ shrink/3-cover        → shrink/2-core
```

It uses your own `git` + `gh` auth — **no GitHub App required**. If `gh` can't open a PR
(not authed, not a collaborator), it prints the compare URL for each slice so you can open
them by hand. The stack is **never pushed unless completeness verifies**.

!!! note "Hosted / webhook-driven shrink"
    A GitHub App that clones a repo on a webhook and auto-opens the stack is a separate
    milestone. The async worker (`gitly.shrink.run`) already runs the real engine on a repo
    path; the App layer (installation auth, public webhook) is the remaining piece.

## Validate every slice

Tree-equality proves the *whole* stack reconstructs `head`. But does each slice **build on
its own**? `--check "<cmd>"` runs a build/test command against every slice in isolation —
each slice's commit is checked out into a throwaway **git worktree** and the command runs
there:

```console
$ gitly shrink main HEAD --check "python -m compileall -q ." --pr
...
validating each slice: `python -m compileall -q .`
  ✓ #1  chore: dependencies
  ✓ #2  feat: core
  ✓ #3  test: cover
ok: every slice is green ✅
```

A **red slice blocks `--pr`** (exit 1, nothing pushed) — a slice that fails on its own means
the (heuristic) dependency ordering shipped something too late. Add `--docker <image>` to run
the check inside a container for real environment isolation:

```bash
gitly shrink main HEAD --check "pytest -q" --docker python:3.12 --pr
```

This upgrades the guarantee from *"the stack reconstructs head"* to *"…and every slice is
green."*

## Over HTTP

The planning step is also exposed by the backend, so a UI (or your agent) can preview a
stack from a raw diff without touching git:

```bash
curl -s localhost:8000/shrink/analyze \
  -H 'content-type: application/json' \
  -d '{"diff": "<unified diff>", "strength": "balanced"}'
```

A malformed diff returns **400** (the planner uses a strict hunk parser). To run a full
materialize+verify asynchronously, enqueue a job:

```bash
curl -s localhost:8000/shrink/jobs \
  -H 'content-type: application/json' \
  -d '{"repo": "...", "base": "main", "head": "HEAD", "max_lines": 400}'
```

See the [HTTP API reference](../reference/api.md) for the full surface.
