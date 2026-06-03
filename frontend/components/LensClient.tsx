"use client";
import { useState } from "react";
import { analyzeDiff } from "@/lib/clientApi";

const SAMPLE = `diff --git a/src/api/users.ts b/src/api/users.ts
index 1aaaaaa..1bbbbbb 100644
--- a/src/api/users.ts
+++ b/src/api/users.ts
@@ -1,4 +1,4 @@
 import { Router } from 'express';
-import { db } from '@/utils/legacy-db';
+import { db } from '@/lib/database';

 const router = Router();
@@ -12,3 +12,3 @@ router.get('/:id', async (req, res) => {
   const id = req.params.id;
-  const user = await getUser(req.params.id);
+  const user = await fetchUser(req.params.id);
   res.json(user);
@@ -40,3 +40,3 @@ export async function current(session) {
   if (!session) return null;
-  const u = getUser(session.uid);
+  const u = fetchUser(session.uid);
   return u;
diff --git a/src/api/orders.ts b/src/api/orders.ts
index 2aaaaaa..2bbbbbb 100644
--- a/src/api/orders.ts
+++ b/src/api/orders.ts
@@ -8,3 +8,3 @@ export async function owner(order) {
   const order = await findOrder(id);
-  const owner = await getUser(order.userId);
+  const owner = await fetchUser(order.userId);
   return owner;
@@ -22,3 +22,3 @@ export async function adminFor(adminId) {
   await assertAdmin(adminId);
-  const admin = await getUser(adminId);
+  const admin = await getCurrentUser(adminId);
   return admin;
diff --git a/src/api/admin.ts b/src/api/admin.ts
index 3aaaaaa..3bbbbbb 100644
--- a/src/api/admin.ts
+++ b/src/api/admin.ts
@@ -5,3 +5,3 @@ export function lookup(targetId) {
   assertRole('admin');
-  return getUser(targetId);
+  return fetchUser(targetId);
 }
diff --git a/src/services/profile.ts b/src/services/profile.ts
index 8aaaaaa..8bbbbbb 100644
--- a/src/services/profile.ts
+++ b/src/services/profile.ts
@@ -7,3 +7,3 @@ export async function profileFor(uid) {
   if (!uid) throw new Error('no uid');
-  const profile = getUser(uid);
+  const profile = fetchUser(uid);
   return profile.public;
diff --git a/src/db/client.ts b/src/db/client.ts
index 6aaaaaa..6bbbbbb 100644
--- a/src/db/client.ts
+++ b/src/db/client.ts
@@ -1,3 +1,3 @@
 import { Pool } from 'pg';
-import { pool } from '@/utils/legacy-db';
+import { pool } from '@/lib/database';
 export const client = pool;
diff --git a/server/handlers.go b/server/handlers.go
index 4aaaaaa..4bbbbbb 100644
--- a/server/handlers.go
+++ b/server/handlers.go
@@ -10,3 +10,3 @@ package server
 // GetUser returns a user by id.
-func GetUser(w http.ResponseWriter, r *http.Request) {
+func GetUser(ctx context.Context, w http.ResponseWriter, r *http.Request) {
   id := chi.URLParam(r, "id")
@@ -25,3 +25,3 @@ func GetUser(ctx, w, r) {
 // ListUsers returns all users.
-func ListUsers(w http.ResponseWriter, r *http.Request) {
+func ListUsers(ctx context.Context, w http.ResponseWriter, r *http.Request) {
   page := query(r, "page")
diff --git a/server/routes.go b/server/routes.go
index 5aaaaaa..5bbbbbb 100644
--- a/server/routes.go
+++ b/server/routes.go
@@ -14,3 +14,3 @@ func Register(r chi.Router) {
 // Health is the liveness probe.
-func Health(w http.ResponseWriter, r *http.Request) {
+func Health(ctx context.Context, w http.ResponseWriter, r *http.Request) {
   w.WriteHeader(200)
diff --git a/package.json b/package.json
index 7aaaaaa..7bbbbbb 100644
--- a/package.json
+++ b/package.json
@@ -2,3 +2,3 @@
   "name": "acme-api",
-  "version": "2.3.0",
+  "version": "2.4.0",
   "private": true,
`;

const CONF: Record<string, string> = { high: "accent", medium: "ai", low: "" };
const ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

// render `backtick code` spans inside a title/reason
function ticks(s: string) {
  return s.split("`").map((seg, i) => (i % 2 ? <code key={i}>{seg}</code> : <span key={i}>{seg}</span>));
}

function DiffSnip({ hunk }: { hunk: any }) {
  if (!hunk) return null;
  const lines = (hunk.lines || []).slice(0, 14);
  return (
    <div className="diffsnip">
      {lines.map((ln: any, i: number) => {
        const cls = ln.type === "add" ? "add" : ln.type === "remove" ? "rem" : "ctx";
        const g = ln.type === "add" ? "+" : ln.type === "remove" ? "-" : " ";
        return (
          <div className={`dl ${cls}`} key={i}>
            <span className="g">{g}</span>
            {ln.content}
          </div>
        );
      })}
    </div>
  );
}

export default function LensClient() {
  const [diff, setDiff] = useState(SAMPLE);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true); setErr(""); setRes(null);
    try { setRes(await analyzeDiff(diff)); }
    catch (e: any) { setErr(e?.message || "request failed"); }
    finally { setLoading(false); }
  }

  const clusters = res
    ? [...(res.clusters || [])].sort(
        (a, b) => (ORDER[a.confidence] - ORDER[b.confidence]) || (b.site_count - a.site_count),
      )
    : [];

  return (
    <div className="card-grid cols-2" style={{ alignItems: "start" }}>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
          <span className="mono dim" style={{ fontSize: 12 }}>unified diff</span>
          <button className="btn btn-ghost" style={{ padding: "6px 12px" }} onClick={() => setDiff(SAMPLE)}>sample</button>
        </div>
        <textarea className="input" rows={16} value={diff} onChange={(e) => setDiff(e.target.value)} />
        <button className="btn btn-accent" style={{ marginTop: 12 }} onClick={run} disabled={loading}>
          {loading ? "analyzing…" : "Analyze diff →"}
        </button>
      </div>

      <div>
        {err && <div className="callout danger"><span>{err}. Is the backend running on :8000?</span></div>}
        {!res && !err && <div className="card dim">Conceptual clusters appear here. A repeated rename / import migration collapses into one card; deviating sites are flagged as outliers.</div>}
        {res && (
          <>
            <div className="row" style={{ gap: 18, marginBottom: 14 }}>
              <span className="mono dim">{res.stats.files_changed} files</span>
              <span className="mono" style={{ color: "var(--human)" }}>+{res.stats.lines_added}</span>
              <span className="mono" style={{ color: "var(--danger)" }}>−{res.stats.lines_removed}</span>
              <span className="mono dim">{res.stats.cluster_count} clusters · {res.stats.hunk_count} hunks</span>
            </div>
            {clusters.map((c: any) => (
              <div className="cluster-card" key={c.id}>
                <div className="row" style={{ justifyContent: "space-between", gap: 8 }}>
                  <div style={{ fontWeight: 600 }}>{ticks(c.title)}</div>
                  <span className={`pill ${CONF[c.confidence]}`}><span className="dot" />{c.confidence}</span>
                </div>
                <div className="cluster-meta">
                  {c.kind} · {c.site_count} site{c.site_count > 1 ? "s" : ""} · {c.file_count} file{c.file_count > 1 ? "s" : ""}
                </div>
                <DiffSnip hunk={res.hunks?.[c.representative_hunk_id]} />
                {(c.outliers || []).map((o: any, i: number) => (
                  <div className="outlier" key={i}>⚠ {ticks(o.reason)}</div>
                ))}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
