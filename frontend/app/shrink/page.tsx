const slices = [
  { n: 1, title: "config & migrations", lines: 120, dep: "—", tone: "human" },
  { n: 2, title: "auth · token model", lines: 280, dep: "#1", tone: "ai" },
  { n: 3, title: "auth · refresh flow", lines: 310, dep: "#2", tone: "ai" },
  { n: 4, title: "api · routes", lines: 260, dep: "#3", tone: "hybrid" },
  { n: 5, title: "tests", lines: 240, dep: "#3", tone: "human" },
];

export default function ShrinkPage() {
  const total = slices.reduce((s, x) => s + x.lines, 0);
  return (
    <>
      <section className="hero" style={{ paddingBottom: 32 }}>
        <div className="eyebrow reveal">02 · structure</div>
        <h1 className="reveal d1" style={{ fontSize: "clamp(34px,5vw,56px)", marginTop: 14 }}>
          Turn an <span className="stroke">unreviewable</span> megaPR into a <span className="hl">verified stack.</span>
        </h1>
        <p className="hero-sub reveal d2" style={{ maxWidth: 620 }}>
          A 2,000-line PR no human can review becomes a dependency-ordered stack of small sub-PRs —
          each one compiles and tests on its own.
        </p>
      </section>

      <section style={{ paddingTop: 0 }}>
        <div className="card-grid cols-2" style={{ alignItems: "start" }}>
          <div className="card reveal d2">
            <div className="mono dim" style={{ fontSize: 12, marginBottom: 12 }}>before · one PR</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
              <span className="big" style={{ fontFamily: "var(--font-display)", fontSize: 44, fontWeight: 700, color: "var(--danger)" }}>{total}</span>
              <span className="dim">lines · 1 diff · unreviewable</span>
            </div>
            <div style={{ marginTop: 16, height: 40, borderRadius: 8, background: "color-mix(in srgb, var(--danger) 22%, var(--surface))", border: "1px solid color-mix(in srgb, var(--danger) 35%, transparent)" }} />
            <div className="callout warn" style={{ marginTop: 18 }}>
              <span>Defect detection collapses above ~400 lines (SmartBear; Google caps CLs near 1,000).</span>
            </div>
          </div>

          <div className="reveal d3">
            <div className="mono dim" style={{ fontSize: 12, marginBottom: 12 }}>after · {slices.length} stacked sub-PRs</div>
            <div style={{ display: "grid", gap: 10 }}>
              {slices.map((s) => (
                <div className="card" key={s.n} style={{ padding: 16, display: "grid", gridTemplateColumns: "auto 1fr auto", alignItems: "center", gap: 14 }}>
                  <span className="mono" style={{ color: "var(--accent)", fontSize: 13 }}>#{s.n}</span>
                  <div>
                    <div style={{ fontWeight: 600 }}>{s.title}</div>
                    <div className="mono dim" style={{ fontSize: 11.5 }}>{s.lines} lines · depends on {s.dep}</div>
                  </div>
                  <span className={`pill ${s.tone}`}><span className="dot" />reviewable</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="callout ok" style={{ marginTop: 24 }}>
          <div>
            <strong className="mono">completeness guarantee</strong>
            <div style={{ marginTop: 6, color: "var(--text-dim)" }}>
              The stack is accepted only if <code className="mono accent">tree(base + all slices) == tree(head)</code> — exact git
              object-ID equality. A split can never silently lose or duplicate a change.
            </div>
          </div>
        </div>

        <p className="dim" style={{ marginTop: 22, fontSize: 14 }}>
          The shrink engine ports from <span className="mono">pr-shrinker</span> — see <span className="mono">MIGRATION.md</span>.
        </p>
      </section>
    </>
  );
}
