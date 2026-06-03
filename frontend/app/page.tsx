import Link from "next/link";

const codeLines = [
  { ln: 12, a: "human", src: "class SessionStore:", who: "you" },
  { ln: 13, a: "ai", src: "    def refresh(self, token):", who: "claude-opus-4-8" },
  { ln: 14, a: "ai", src: "        claims = jwt.decode(token, KEY)", who: "claude-opus-4-8" },
  { ln: 15, a: "hybrid", src: "        if claims.exp < now(): raise", who: "62% human" },
  { ln: 16, a: "ai", src: "        return self.issue(claims.sub)", who: "gpt-4o" },
  { ln: 17, a: "human", src: "        # TODO: rotate signing key", who: "you" },
];

const flow = [
  { key: "copilot", stage: "01 · author", href: "/copilot", tone: "accent", status: "interactive demo",
    desc: "Commit correctly — semantic staging, absorb, safe checkpoints, and a secret firewall." },
  { key: "shrink", stage: "02 · structure", href: "/shrink", tone: "ai", status: "engine porting",
    desc: "Split a megaPR into a verified stack of small, dependency-ordered sub-PRs." },
  { key: "lens", stage: "03 · review", href: "/lens", tone: "human", status: "live parser",
    desc: "Re-render a diff as conceptual change clusters with outlier flagging." },
];

const features = [
  { t: "Built for vibe coders", d: "Meets you inside your AI agent via an MCP server + git hooks — no new CLI to learn." },
  { t: "Never leak a secret", d: "Layered scanning at three gates; prompts are redacted before they ever touch disk." },
  { t: "Provenance you can prove", d: "Line-level authorship: model, prompt, human-edit ratio, and whether it was reviewed." },
];

export default function Home() {
  return (
    <>
      <section className="hero">
        <div className="hero-grid">
          <div>
            <div className="eyebrow reveal">git quality · ai-authorship era</div>
            <h1 className="reveal d1" style={{ marginTop: 18 }}>
              Know who <span className="hl">really wrote</span> your <span className="stroke">code.</span>
            </h1>
            <p className="hero-sub reveal d2">
              gitly helps anyone — expert or vibe coder — commit cleanly, ship small reviewable PRs,
              and trace every line back to the model, prompt, and human behind it.
            </p>
            <div className="hero-cta reveal d3">
              <Link href="/trace" className="btn btn-accent">Open the trace dashboard →</Link>
              <a href="#pillars" className="btn btn-ghost">See the four pillars</a>
            </div>
            <div className="hero-stats reveal d4">
              <div className="hero-stat"><div className="n">4</div><div className="l">pillars</div></div>
              <div className="hero-stat"><div className="n accent">1 diff</div><div className="l">shared kernel</div></div>
              <div className="hero-stat"><div className="n">&lt;200</div><div className="l">lines / good PR</div></div>
            </div>
          </div>

          <div className="codeblock reveal d3">
            <div className="cb-head">
              <span className="cb-dots"><i /><i /><i /></span>
              auth/session.py
              <span className="cb-tag">gitly trace</span>
            </div>
            <div className="code">
              {codeLines.map((l, i) => (
                <div className="cl" data-a={l.a} key={i} style={{ animationDelay: `${0.35 + i * 0.09}s` }}>
                  <span className="ln">{l.ln}</span>
                  <span className="src">{l.src}</span>
                  <span className={`who ${l.a}`}>{l.who}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="pillars">
        <div className="section-head">
          <div className="eyebrow">the pipeline</div>
          <h2>Four pillars, one git-native kernel</h2>
          <p className="lead">Every change flows author → structure → review — with provenance recorded underneath all of it.</p>
        </div>

        <div className="pipe">
          {flow.map((p) => (
            <Link href={p.href} className="card pillar pipe-node" key={p.key}>
              <div className="pn">{p.stage}</div>
              <h3>{p.key}</h3>
              <p className="dim" style={{ fontSize: 14 }}>{p.desc}</p>
              <div className="status"><span className={`pill ${p.tone}`}><span className="dot" />{p.status}</span></div>
            </Link>
          ))}
        </div>

        <Link href="/trace" className="trace-band">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <div className="mono accent" style={{ fontSize: 12 }}>trace · provenance ground-truth</div>
              <h3 style={{ fontSize: 20, marginTop: 6 }}>Who · which model · which prompt · how much a human changed it</h3>
            </div>
            <span className="pill accent"><span className="dot" />live</span>
          </div>
        </Link>
      </section>

      <section style={{ paddingTop: 0 }}>
        <div className="card-grid cols-3">
          {features.map((f) => (
            <div className="card" key={f.t}>
              <h3 style={{ fontSize: 17 }}>{f.t}</h3>
              <p className="dim" style={{ marginTop: 8, fontSize: 14 }}>{f.d}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
