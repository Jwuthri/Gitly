"use client";
import { useState } from "react";
import { analyzeDiff } from "@/lib/clientApi";

const SAMPLE = `diff --git a/src/auth.py b/src/auth.py
index 1111111..2222222 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,7 +10,7 @@ def login(user):
-    token = make_token(user)
+    token = issue_token(user)
@@ -22,6 +22,7 @@ def refresh(user):
-    return make_token(user)
+    return issue_token(user)
+    log.info("refreshed")
diff --git a/src/api.py b/src/api.py
index 3333333..4444444 100644
--- a/src/api.py
+++ b/src/api.py
@@ -5,7 +5,7 @@ def handler(u):
-    t = make_token(u)
+    t = issue_token(u)
`;

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
        {!res && !err && <div className="card dim">Parsed structure appears here. Clustering ports from the lens engine (pr-visual-diff).</div>}
        {res && (
          <>
            <div className="card-grid cols-2" style={{ marginBottom: 14 }}>
              <div className="card stat"><div className="lbl">files</div><div className="big">{res.files}</div></div>
              <div className="card stat"><div className="lbl">changed lines</div><div className="big accent">{res.changed_lines}</div></div>
            </div>
            <div style={{ display: "grid", gap: 10 }}>
              {(res.skeleton ?? []).map((f: any, i: number) => (
                <div className="card" key={i} style={{ padding: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div className="file mono">{f.path}</div>
                    <div className="mono dim" style={{ fontSize: 11.5, marginTop: 4 }}>{f.hunks} hunk(s)</div>
                  </div>
                  <span className={`pill ${f.change === "add" ? "human" : f.change === "delete" ? "danger" : "ai"}`}>
                    <span className="dot" />{f.change}
                  </span>
                </div>
              ))}
            </div>
            <div className="callout warn" style={{ marginTop: 14 }}>
              <span><strong>Clustering next:</strong> {String(res.clusters)}</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
