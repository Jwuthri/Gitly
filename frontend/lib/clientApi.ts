// Browser-side calls (from client components) go to the public URL via the host.
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function analyzeDiff(diff: string) {
  const r = await fetch(`${API}/lens/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ diff }),
  });
  if (!r.ok) throw new Error(`lens/analyze ${r.status}`);
  return r.json();
}

export async function scanSecrets(text: string) {
  const r = await fetch(`${API}/copilot/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok) throw new Error(`copilot/scan ${r.status}`);
  return r.json();
}

export async function getTraceTree(repo: string) {
  const r = await fetch(`${API}/trace/tree?repo=${encodeURIComponent(repo)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`trace/tree ${r.status}`);
  return r.json();
}

export async function getTraceFile(repo: string, path: string) {
  const r = await fetch(`${API}/trace/file?repo=${encodeURIComponent(repo)}&path=${encodeURIComponent(path)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`trace/file ${r.status}`);
  return r.json();
}

export async function planShrink(diff: string, strength = "balanced") {
  const r = await fetch(`${API}/shrink/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ diff, strength }),
  });
  if (!r.ok) throw new Error(`shrink/analyze ${r.status}`);
  return r.json();
}
