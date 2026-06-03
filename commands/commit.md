---
description: Commit the current changes cleanly — secret-scanned, never to a protected branch.
---
Commit the current working/staged changes using the **gitly_safe_commit** MCP tool.

- Infer a clear, conventional commit message from the diff. If the user provided one, use it: "$ARGUMENTS".
- If gitly reports secrets, do **not** retry — surface the findings and stop so the user can remove them.
- If gitly refuses because the branch is protected, offer to create a feature branch first.
