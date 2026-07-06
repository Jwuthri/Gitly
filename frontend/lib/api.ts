// Browser (client-side) calls go to the public URL via the host. Server-side calls (SSR
// inside the container) must use the internal service URL, because "localhost" inside the
// frontend container is NOT the backend.
const PUBLIC_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SERVER_API = process.env.API_URL_INTERNAL ?? PUBLIC_API;
const API = typeof window === "undefined" ? SERVER_API : PUBLIC_API;

// Surface the response body in errors — "trace/summary 500" alone is undebuggable.
async function getJson(path: string, label: string) {
  const r = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!r.ok) {
    const body = await r.text().catch(() => "");
    throw new Error(`${label} ${r.status}${body ? `: ${body.slice(0, 200)}` : ""}`);
  }
  return r.json();
}

export async function getTraceSummary(repo: string) {
  return getJson(`/trace/summary?repo=${encodeURIComponent(repo)}`, "trace/summary");
}

export async function getTraceRecords(repo: string) {
  return getJson(`/trace/records?repo=${encodeURIComponent(repo)}`, "trace/records");
}
