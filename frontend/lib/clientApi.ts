// Browser-side calls (from client components) go to the public URL via the host.
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Surface the response body in errors — a bare status code is undebuggable in the UI.
async function req(path: string, label: string, init?: RequestInit) {
  const r = await fetch(`${API}${path}`, init);
  if (!r.ok) {
    const body = await r.text().catch(() => "");
    throw new Error(`${label} ${r.status}${body ? `: ${body.slice(0, 200)}` : ""}`);
  }
  return r.json();
}

const post = (path: string, label: string, body: unknown) =>
  req(path, label, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const analyzeDiff = (diff: string) => post("/lens/analyze", "lens/analyze", { diff });

export const scanSecrets = (text: string) => post("/copilot/scan", "copilot/scan", { text });

export const getTraceTree = (repo: string) =>
  req(`/trace/tree?repo=${encodeURIComponent(repo)}`, "trace/tree", { cache: "no-store" });

export const getTraceFile = (repo: string, path: string) =>
  req(`/trace/file?repo=${encodeURIComponent(repo)}&path=${encodeURIComponent(path)}`, "trace/file", { cache: "no-store" });

export const planShrink = (diff: string, strength = "balanced") =>
  post("/shrink/analyze", "shrink/analyze", { diff, strength });
