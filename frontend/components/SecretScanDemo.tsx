"use client";
import { useState } from "react";
import { scanSecrets } from "@/lib/clientApi";

const SAMPLE = `DATABASE_URL = "postgres://app:s3cr3t@db/prod"
ANTHROPIC_API_KEY = "sk-ant-api03-Abc123Def456Ghi789Jkl012Mno345"
def handler():
    return ok()`;

export default function SecretScanDemo() {
  const [text, setText] = useState(SAMPLE);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true); setErr(""); setRes(null);
    try { setRes(await scanSecrets(text)); }
    catch (e: any) { setErr(e?.message || "request failed"); }
    finally { setLoading(false); }
  }

  return (
    <div className="card-grid cols-2" style={{ alignItems: "start" }}>
      <div className="card">
        <div className="mono dim" style={{ fontSize: 12, marginBottom: 12 }}>staged changes</div>
        <textarea className="input" rows={8} value={text} onChange={(e) => setText(e.target.value)} />
        <button className="btn btn-accent" style={{ marginTop: 12 }} onClick={run} disabled={loading}>
          {loading ? "scanning…" : "Scan for secrets →"}
        </button>
      </div>

      <div>
        {err && <div className="callout danger"><span>{err}. Is the backend running on :8000?</span></div>}
        {!res && !err && <div className="card dim">Findings appear here.</div>}
        {res && (res.clean ? (
          <div className="callout ok"><span><strong>Clean.</strong> No secrets detected — safe to commit.</span></div>
        ) : (
          <>
            <div className="callout danger" style={{ marginBottom: 14 }}>
              <span><strong>Commit blocked — {res.findings.length} secret(s) found.</strong></span>
            </div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>type</th><th>line</th></tr></thead>
                <tbody>
                  {res.findings.map((f: any, i: number) => (
                    <tr key={i}>
                      <td><span className="pill danger"><span className="dot" />{f.kind}</span></td>
                      <td className="mono">{f.line}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {res.redacted_preview && (
              <div className="card" style={{ marginTop: 14 }}>
                <div className="mono dim" style={{ fontSize: 11.5, marginBottom: 8 }}>redacted before any LLM call or storage</div>
                <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: 12, color: "var(--text-dim)", margin: 0 }}>{res.redacted_preview}</pre>
              </div>
            )}
          </>
        ))}
      </div>
    </div>
  );
}
