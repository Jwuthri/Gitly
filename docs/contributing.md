# Contributing & maintenance

How to work on gitly locally, and how the project builds, tests, and **publishes itself**.

## Local setup

```bash
git clone https://github.com/Jwuthri/Gitly.git
cd Gitly
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # core + pytest + ruff (no server deps needed for tests)
```

Run the checks the way CI does:

```bash
ruff check shared backend workers     # lint  (make fmt = ruff --fix)
pytest -q                             # tests (make test)
```

## Working on the docs

The documentation is [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) —
plain Markdown in `docs/` plus `mkdocs.yml`.

```bash
pip install -e ".[docs]"     # mkdocs-material
make docs-serve              # live-reload preview → http://localhost:8001/Gitly/
make docs-build              # strict build into ./site (fails on broken links/nav)
```

Always run `make docs-build` (a `--strict` build) before opening a PR — it catches broken
internal links and pages missing from the nav, which is what would otherwise slip through.

Adding a page: create `docs/<section>/<page>.md` and add it to the `nav:` in `mkdocs.yml`.

## How CI works

`.github/workflows/ci.yml` runs on **every PR and every push to `master`**:

```
ruff check shared backend workers     # lint
pytest -q                             # 36 tests
```

It installs only `.[dev]` (the lean set) — so a green CI run is also a standing proof that
the engines and the `gitly` CLI need **no** server dependencies.

## How the docs get published

This is fully automated — you never touch the published output by hand.

`.github/workflows/docs.yml` fires whenever `master` changes a docs file (`docs/**`,
`mkdocs.yml`, or the workflow itself) and runs one command — `mkdocs gh-deploy --force --no-history`:

```
push to master (docs changed)
      │
      ▼
 Action runs  →  mkdocs build      (docs/*.md  →  site/  static HTML)
      │
      ▼
 force-push the built HTML onto the  gh-pages  branch
      │
      ▼
 GitHub Pages republishes           (~1 min → https://jwuthri.github.io/Gitly/)
```

Key points:

- **`master` = source** (the Markdown you edit). **`gh-pages` = generated output** (HTML).
  Pages serves static HTML, not Markdown, so the build step is mandatory.
- **`gh-pages` is regenerated, never hand-edited.** `gh-deploy` force-pushes a fresh build
  each time; any manual change there is overwritten on the next deploy. `--no-history` keeps
  the branch to a single throwaway commit so it doesn't bloat.
- **Only docs changes on `master` trigger it.** Backend-only pushes don't rebuild the docs;
  docs pushed to a feature branch don't either (preview those with `make docs-serve`).
- **Manual rebuild:** the workflow's `workflow_dispatch` adds a **Run workflow** button under
  the repo's **Actions** tab.

### One-time Pages setup

After the first deploy creates `gh-pages`: repo **Settings → Pages → Build and deployment →
Source: "Deploy from a branch" → `gh-pages` / `root`**. The live URL then appears at the top
of that same Settings → Pages screen.

!!! note "Alternative: no `gh-pages` branch"
    Pages can instead be built and served straight from a GitHub Action artifact (Source =
    **"GitHub Actions"**), which removes the `gh-pages` branch entirely. The branch method
    here is MkDocs's canonical recommendation; both rebuild on every push.

## Committing — gitly eats its own dog food

This repo is developed *with* gitly, so the same guardrails apply to contributors:

- `gitly commit` won't stage `.env`, keys, or build junk, and **blocks secrets**.
- `gitly commit --split` is handy for carving a large change into reviewable commits.
- Test fixtures or docs that must contain an example secret carry a **`gitly:allow`**
  pragma on that line — the commit gate skips it, but redaction still strips it before any
  LLM call (see [Security](security.md#allowlisting-false-positives)).
