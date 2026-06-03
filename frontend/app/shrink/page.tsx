import ShrinkClient from "@/components/ShrinkClient";

export default function ShrinkPage() {
  return (
    <>
      <section className="hero" style={{ paddingBottom: 24 }}>
        <div className="eyebrow reveal">02 · structure</div>
        <h1 className="reveal d1" style={{ fontSize: "clamp(32px,4.6vw,52px)", marginTop: 14 }}>
          Turn an <span className="stroke">unreviewable</span> megaPR into a <span className="hl">verified stack.</span>
        </h1>
        <p className="hero-sub reveal d2" style={{ maxWidth: 620 }}>
          A big PR no human can review becomes a dependency-ordered stack of small sub-PRs —
          grouped by intent (deps → source → tests → docs), each one reviewable on its own.
        </p>
      </section>

      <section style={{ paddingTop: 0 }}>
        <ShrinkClient />
      </section>

      <section style={{ paddingTop: 0 }}>
        <div className="callout ok">
          <div>
            <strong className="mono">completeness guarantee</strong>
            <div style={{ marginTop: 6, color: "var(--text-dim)" }}>
              Each level rebuilds fresh from the merge-base, and the stack is accepted only if{" "}
              <code className="mono accent">tree(base + all slices) == tree(head)</code> — exact git object-ID
              equality. A split can never silently lose or duplicate a change.
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
