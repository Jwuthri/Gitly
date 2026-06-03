"use client";
import { useState } from "react";
import { planShrink } from "@/lib/clientApi";

const SAMPLE = `diff --git a/pyproject.toml b/pyproject.toml
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -8,3 +8,4 @@ dependencies = [
   "fastapi>=0.115",
+  "redis>=5.0",
   "pydantic>=2.7",
 ]
diff --git a/src/auth/session.py b/src/auth/session.py
--- a/src/auth/session.py
+++ b/src/auth/session.py
@@ -10,2 +10,3 @@ class SessionStore:
   def get(self, sid):
-      return self._mem.get(sid)
+      return self._redis.get(sid)
+      # cache-through
diff --git a/src/auth/login.py b/src/auth/login.py
--- a/src/auth/login.py
+++ b/src/auth/login.py
@@ -5,2 +5,4 @@ def login(user):
   token = issue_token(user)
+  store.persist(token)
+  audit("login", user)
   return token
diff --git a/src/api/routes.py b/src/api/routes.py
--- a/src/api/routes.py
+++ b/src/api/routes.py
@@ -20,2 +20,3 @@ def register(app):
   app.post("/login", login_handler)
+  app.post("/logout", logout_handler)
   app.get("/me", me_handler)
diff --git a/tests/test_auth.py b/tests/test_auth.py
--- a/tests/test_auth.py
+++ b/tests/test_auth.py
@@ -1,2 +1,5 @@
 def test_login():
     assert login("u")
+
+def test_logout():
+    assert logout("u")
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,2 +1,3 @@
 # acme
+Now with Redis-backed sessions.
 Run with docker compose.
`;

const LEVELS = ["gentle", "balanced", "aggressive"] as const;

export default function ShrinkClient() {
  const [diff, setDiff] = useState(SAMPLE);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [strength, setStrength] = useState<string>("balanced");

  async function run(s: string = strength) {
    setLoading(true); setErr(""); setRes(null);
    try { setRes(await planShrink(diff, s)); }
    catch (e: any) { setErr(e?.message || "request failed"); }
    finally { setLoading(false); }
  }

  function pick(s: string) {
    setStrength(s);
    if (res || err) run(s); // re-plan live once there's a result
  }

  return (
    <div className="card-grid cols-2" style={{ alignItems: "start" }}>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
          <span className="mono dim" style={{ fontSize: 12 }}>unified diff (a megaPR)</span>
          <button className="btn btn-ghost" style={{ padding: "6px 12px" }} onClick={() => setDiff(SAMPLE)}>sample</button>
        </div>
        <textarea className="input" rows={14} value={diff} onChange={(e) => setDiff(e.target.value)} />

        <div style={{ marginTop: 14 }}>
          <div className="mono dim" style={{ fontSize: 11, letterSpacing: ".14em", textTransform: "uppercase", marginBottom: 7 }}>
            shrink strength
          </div>
          <div className="seg">
            {LEVELS.map((s) => (
              <button key={s} className={strength === s ? "active" : ""} onClick={() => pick(s)}>{s}</button>
            ))}
          </div>
          <div className="mono dim" style={{ fontSize: 10.5, marginTop: 7 }}>
            fewer, larger PRs &nbsp;⟷&nbsp; more, smaller PRs
          </div>
        </div>

        <button className="btn btn-accent" style={{ marginTop: 16 }} onClick={() => run()} disabled={loading}>
          {loading ? "planning…" : "Propose a stack →"}
        </button>
      </div>

      <div>
        {err && <div className="callout danger"><span>{err}. Is the backend running on :8000?</span></div>}
        {!res && !err && <div className="card dim">The proposed stack of small, dependency-ordered sub-PRs appears here.</div>}
        {res && (
          <>
            <div className="row" style={{ gap: 14, marginBottom: 14, alignItems: "baseline" }}>
              <span className="mono dim">{res.original_lines} lines / {res.original_files} files</span>
              <span className="mono accent">→ {res.slices.length} sub-PRs</span>
              <span className="pill" style={{ marginLeft: "auto" }}><span className="dot" />{res.strength}</span>
            </div>
            <div style={{ display: "grid", gap: 10 }}>
              {res.slices.map((s: any) => (
                <div className="card" key={s.order} style={{ padding: 16, display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 14, alignItems: "center" }}>
                  <span className="mono" style={{ color: "var(--accent)", fontSize: 13 }}>#{s.order}</span>
                  <div>
                    <div style={{ fontWeight: 600 }}>{s.title}</div>
                    <div className="mono dim" style={{ fontSize: 11.5, marginTop: 4 }}>
                      {s.lines} ln · {s.files} files{s.depends_on?.length ? ` · after #${s.depends_on.join(", #")}` : ""}
                    </div>
                  </div>
                  <span className="pill ai"><span className="dot" />reviewable</span>
                </div>
              ))}
            </div>
            <div className="callout ok" style={{ marginTop: 14 }}>
              <span>{res.note} Run <code>gitly shrink &lt;base&gt; &lt;head&gt; --strength {res.strength}</code> to materialize the stack and verify <code>tree(base + slices) == tree(head)</code>.</span>
            </div>
            {(res.notes || []).map((n: string, i: number) => (
              <div className="callout warn" style={{ marginTop: 10 }} key={i}><span>{n}</span></div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
