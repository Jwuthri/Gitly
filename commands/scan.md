---
description: Scan the staged changes for secrets before committing.
---
Use the **gitly_scan_secrets** MCP tool with `staged: true` to check the staged diff for secrets (API keys, tokens, private keys).

Report any findings clearly with their line numbers. If clean, confirm it's safe to commit.
