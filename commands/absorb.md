---
description: Fold uncommitted changes into the commit(s) they belong to and re-stack (gitly absorb).
---
Use the **gitly_absorb** MCP tool to fold the working-tree changes into the correct earlier commit(s) and re-stack the branch.

- If the user named a target commit in "$ARGUMENTS", pass it as `into`.
- Afterward, report which commit(s) absorbed which files.
- If gitly aborts (conflict, protected branch, or already-pushed history), explain why and stop — nothing was changed.
