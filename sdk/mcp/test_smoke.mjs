// Smoke test: connect to the built gitly MCP server with the official MCP client,
// list tools, and exercise a git-only tool + a backend-backed tool.
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

const transport = new StdioClientTransport({
  command: "node",
  args: [join(here, "dist/index.js")],
  env: { ...process.env, GITLY_API_URL: process.env.GITLY_API_URL || "http://localhost:8000" },
});
const client = new Client({ name: "smoke", version: "0" }, { capabilities: {} });
await client.connect(transport);

const { tools } = await client.listTools();
console.log("tools:", tools.map((t) => t.name).join(", "));

const status = await client.callTool({ name: "gitly_status", arguments: { cwd: here } });
console.log("gitly_status ->", String(status.content?.[0]?.text || "").split("\n")[0]);

const scan = await client.callTool({
  name: "gitly_scan_secrets",
  arguments: { text: 'KEY = "sk-ant-api03-Abc123Def456Ghi789Jkl012Mno345"' },
});
console.log("gitly_scan_secrets ->", String(scan.content?.[0]?.text || "").split("\n")[0]);

await client.close();
process.exit(0);
