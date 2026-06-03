import AuthorshipBar from "@/components/AuthorshipBar";
import TraceExplorer from "@/components/TraceExplorer";
import { getTraceSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TracePage({ searchParams }: { searchParams: { repo?: string } }) {
  const repo = (searchParams.repo ?? "demo-app").trim();
  let summary: any = null;
  let error = "";

  if (repo) {
    try {
      summary = await getTraceSummary(repo);
    } catch {
      error = "Could not reach the gitly API.";
    }
  }

  const pct = summary && summary.total_lines ? Math.round((100 * summary.ai_lines) / summary.total_lines) : 0;
  const models: [string, number][] = summary?.by_model
    ? (Object.entries(summary.by_model) as [string, number][]).sort((a, b) => b[1] - a[1])
    : [];
  const maxModel = models.length ? Math.max(...models.map((m) => m[1])) : 1;
  const labelStyle = { fontSize: 11, letterSpacing: ".14em", textTransform: "uppercase" as const, color: "var(--text-faint)" };

  return (
    <>
      <section className="hero" style={{ paddingBottom: 22 }}>
        <div className="eyebrow reveal">trace · provenance</div>
        <h1 className="reveal d1" style={{ fontSize: "clamp(30px,4.4vw,50px)", marginTop: 14 }}>
          git blame tells you who <span className="stroke">typed</span> it.<br />
          trace tells you who <span className="hl">wrote</span> it.
        </h1>
        <form method="get" className="row reveal d2" style={{ marginTop: 22, maxWidth: 420 }}>
          <input className="input" name="repo" defaultValue={repo} placeholder="repo name" style={{ flex: 1 }} />
          <button className="btn btn-accent" type="submit">Load</button>
        </form>
      </section>

      {error && (
        <div className="callout danger">{error} Is the backend running? Try <span className="mono">&nbsp;make up</span>.</div>
      )}

      {summary && summary.total_lines > 0 && (
        <>
          <section style={{ paddingTop: 0 }}>
            <div className="card-grid cols-4">
              <div className="card stat"><div className="lbl">tracked lines</div><div className="big">{summary.total_lines.toLocaleString()}</div><div className="sub">with provenance</div></div>
              <div className="card stat"><div className="lbl">AI authored</div><div className="big accent">{pct}%</div><div className="sub">{summary.ai_lines.toLocaleString()} lines</div></div>
              <div className="card stat"><div className="lbl">hybrid</div><div className="big" style={{ color: "var(--hybrid)" }}>{summary.hybrid_lines.toLocaleString()}</div><div className="sub">AI + human edits</div></div>
              <div className="card stat"><div className="lbl">unreviewed AI</div><div className="big" style={{ color: "var(--warn)" }}>{summary.unreviewed_ai_lines.toLocaleString()}</div><div className="sub">needs a human</div></div>
            </div>
          </section>

          <section style={{ paddingTop: 0 }}>
            <div className="card-grid cols-2" style={{ alignItems: "start" }}>
              <div className="card">
                <div className="mono" style={labelStyle}>authorship mix</div>
                <div style={{ marginTop: 18 }}>
                  <AuthorshipBar ai={summary.ai_lines} human={summary.human_lines} hybrid={summary.hybrid_lines} />
                </div>
              </div>
              <div className="card">
                <div className="mono" style={labelStyle}>by model</div>
                <div style={{ marginTop: 14 }}>
                  {models.map(([name, count]) => (
                    <div className="mbar-row" key={name}>
                      <span className="name">{name}</span>
                      <span className="mbar"><span style={{ width: `${Math.round((count / maxModel) * 100)}%` }} /></span>
                      <span className="val">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {summary.unreviewed_ai_lines > 0 && (
            <section style={{ paddingTop: 0 }}>
              <div className="callout warn">
                <span><strong>{summary.unreviewed_ai_lines.toLocaleString()} AI-authored lines have no human review.</strong> These are the lines to look at first.</span>
              </div>
            </section>
          )}

          <section style={{ paddingTop: 0 }}>
            <div className="section-head" style={{ marginBottom: 18 }}>
              <h2 style={{ fontSize: 24 }}>Browse by file</h2>
              <p className="lead" style={{ fontSize: 15 }}>Pick a file to see every line annotated with who — or what — wrote it.</p>
            </div>
            <TraceExplorer repo={repo} />
          </section>
        </>
      )}

      {summary && summary.total_lines === 0 && !error && (
        <div className="callout ok">
          <span>No provenance yet for <span className="mono">{repo}</span>. Seed demo data with <span className="mono">make seed</span> or <span className="mono">python3 scripts/seed_demo.py --repo {repo}</span>.</span>
        </div>
      )}
    </>
  );
}
