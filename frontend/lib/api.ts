// Browser (client-side) calls go to the public URL via the host. Server-side calls (SSR
// inside the container) must use the internal service URL, because "localhost" inside the
// frontend container is NOT the backend.
const PUBLIC_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SERVER_API = process.env.API_URL_INTERNAL ?? PUBLIC_API;
const API = typeof window === "undefined" ? SERVER_API : PUBLIC_API;

export async function getTraceSummary(repo: string) {
  const r = await fetch(`${API}/trace/summary?repo=${encodeURIComponent(repo)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`trace/summary ${r.status}`);
  return r.json();
}

export async function getTraceRecords(repo: string) {
  const r = await fetch(`${API}/trace/records?repo=${encodeURIComponent(repo)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`trace/records ${r.status}`);
  return r.json();
}
