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
