---
description: Propose splitting the current change into a verified stack of small PRs.
---
Use the **gitly_shrink** MCP tool to propose a verified stack of small, dependency-ordered sub-PRs for the current branch (base..HEAD).

Summarize the proposed sub-PRs in order, with their sizes and dependencies. Remind the user that `gitly shrink <base> <head>` materializes + verifies the stack locally.
