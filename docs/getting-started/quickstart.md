# Quickstart

A five-minute tour of the things you'll use every day. Assumes the [CLI is
installed](installation.md).

## 1. Commit cleanly

Stop typing `git add . && git commit -m "wip"`. Let gitly stage the safe files and write
a conventional message from the diff:

```console
$ gitly commit
Committed e3b5f24 on feature (1 file): docs: update README.md
```

- It **never stages** `.env`, keys, or build junk — even with `-a`.
- It **refuses protected branches** (`main`/`master`/`develop`/`release`).
- It **blocks secrets** before they're ever committed.

Bring your own message any time:

```bash
gitly commit -m "feat: add rate limiter"
gitly commit -a              # also include new/untracked files (still skips .env)
gitly commit --path src/api  # stage only what you name
```

## 2. Split a messy working tree

Made twelve unrelated changes at once? Carve them into reviewable commits — one per
concern:

```console
$ gitly commit --split -a
Split into commits:
  167cf42  chore: update package.json    [1 file]
  b4a4934  feat: add rate limiter        [1 file]
  35bc6ac  test: cover rate limiter      [1 file]
  bb0f28e  docs: document the limiter     [1 file]
```

## 3. Absorb a follow-up edit

Fixed a typo that belongs in an earlier commit? Don't create `fix typo` noise — fold it
into the commit it belongs to and re-stack automatically:

```console
$ gitly absorb
Absorbed 1 file change(s) into 1 commit(s): a739f08. History re-stacked.
```

## 4. See who wrote what

```bash
gitly trace app/api.py        # per-line: AI (with model) vs human, reviewed or not
gitly trace --summary         # repo rollup: % AI, by model, unreviewed-AI lines
```

## 5. Shrink a big branch into a stack

```console
$ gitly shrink main HEAD --strength balanced
1320 lines / 18 files  ->  4 slices
  #1  chore: dependencies  [40 ln / 2 files]
  #2  feat: core engine    [220 ln / 5 files]  (after #1)
  ...
ok: completeness verified — tree(base + slices) == tree(head)
```

## 6. Turn on the intelligence (optional)

The messages above were written offline by the heuristic. For sharper ones, give gitly a
brain — once:

=== "Use Claude Code (no key)"

    Already have Claude Code? Nothing to configure — gitly detects it.

    ```console
    $ gitly config
    active provider : claude-code
    claude code     : available
    ```

=== "Use an API key"

    Drop it in `.env` (auto-loaded) …

    ```bash
    echo 'OPENAI_API_KEY=sk-...' >> .env
    ```

    … or store it with `gitly auth`:

    ```console
    $ gitly auth
    gitly brain — how should I write commit messages & splits?
      1. claude-code   (detected)
      2. openai
      3. anthropic
      4. heuristic
    Choose [1-4]: 2
    openai API key: ********
    Saved -> active provider: openai
    ```

!!! success "Your keys are safe"
    Every diff is **secret-redacted before it reaches any model**, the key is stored at
    `~/.config/gitly/config.json` with `chmod 600`, and `.env` can never be committed.
    More in [Security](../security.md).

Next, dig into each pillar — start with [Copilot](../pillars/copilot.md).
