import SecretScanDemo from "@/components/SecretScanDemo";

const caps = [
  { t: "gitly commit", s: "planned", tone: "", d: 'Semantic staging + a real conventional message instead of git add . && commit -m "wip".' },
  { t: "gitly absorb", s: "planned", tone: "", d: "Amend current edits into the right earlier commit and auto-restack — painless rebasing." },
  { t: "gitly checkpoint", s: "planned", tone: "", d: "Safe, restorable save-points so you can experiment fearlessly." },
  { t: "gitly scan", s: "live", tone: "accent", d: "Layered secret firewall at the agent, pre-commit, and pre-push gates." },
];

export default function CopilotPage() {
  return (
    <>
      <section className="hero" style={{ paddingBottom: 24 }}>
        <div className="eyebrow reveal">01 · author</div>
        <h1 className="reveal d1" style={{ fontSize: "clamp(32px,4.6vw,52px)", marginTop: 14 }}>
          Commit like a pro — <span className="hl">without knowing git.</span>
        </h1>
        <p className="hero-sub reveal d2" style={{ maxWidth: 640 }}>
          The copilot lives inside your AI agent (MCP + git hooks). It stages by intent, writes real commit
          messages, makes rebasing painless, and stops secrets before they're ever committed.
        </p>
      </section>

      <section style={{ paddingTop: 0 }}>
        <div className="card-grid cols-2">
          {caps.map((c) => (
            <div className="card" key={c.t}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <h3 className="mono" style={{ fontSize: 16 }}>{c.t}</h3>
                <span className={`pill ${c.tone}`}><span className="dot" />{c.s}</span>
              </div>
              <p className="dim" style={{ marginTop: 8, fontSize: 14 }}>{c.d}</p>
            </div>
          ))}
        </div>
      </section>

      <section style={{ paddingTop: 0 }}>
        <div className="section-head" style={{ marginBottom: 18 }}>
          <div className="eyebrow">live · secret firewall</div>
          <h2 style={{ fontSize: 26 }}>Try to commit a secret</h2>
          <p className="lead">This calls the real backend scanner — the same layered check that runs at every gate.</p>
        </div>
        <SecretScanDemo />
      </section>
    </>
  );
}
