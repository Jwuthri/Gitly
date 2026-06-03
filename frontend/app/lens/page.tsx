import LensClient from "@/components/LensClient";

export default function LensPage() {
  return (
    <>
      <section className="hero" style={{ paddingBottom: 24 }}>
        <div className="eyebrow reveal">03 · review</div>
        <h1 className="reveal d1" style={{ fontSize: "clamp(32px,4.6vw,52px)", marginTop: 14 }}>
          Read a diff as <span className="hl">concepts</span>, not hunks.
        </h1>
        <p className="hero-sub reveal d2" style={{ maxWidth: 600 }}>
          Paste a unified diff. gitly parses it with the shared kernel and groups it — a 47-site rename
          becomes a single reviewable card instead of 47 scattered hunks.
        </p>
      </section>
      <section style={{ paddingTop: 0 }}>
        <LensClient />
      </section>
    </>
  );
}
