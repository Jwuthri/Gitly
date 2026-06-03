export default function AuthorshipBar({ ai, human, hybrid }: { ai: number; human: number; hybrid: number }) {
  const total = Math.max(1, ai + human + hybrid);
  const pc = (n: number) => `${(100 * n) / total}%`;
  return (
    <div>
      <div className="abar">
        <span className="s-ai" style={{ width: pc(ai) }} />
        <span className="s-hybrid" style={{ width: pc(hybrid) }} />
        <span className="s-human" style={{ width: pc(human) }} />
      </div>
      <div className="legend">
        <span><i style={{ background: "var(--ai)" }} />AI · {ai.toLocaleString()}</span>
        <span><i style={{ background: "var(--hybrid)" }} />hybrid · {hybrid.toLocaleString()}</span>
        <span><i style={{ background: "var(--human)" }} />human · {human.toLocaleString()}</span>
      </div>
    </div>
  );
}
