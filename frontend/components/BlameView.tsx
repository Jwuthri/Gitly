type BlameLine = {
  line_no: number;
  content: string;
  author_type: string;
  model: string | null;
  agent: string;
  reviewed: boolean;
  human_edit_ratio: number;
  prompt: string | null;
};

export default function BlameView({ path, lines }: { path: string; lines: BlameLine[] }) {
  return (
    <div className="blame">
      <div className="blame-head mono">
        {path}
        <span className="dim"> · {lines.length} lines</span>
      </div>
      <div className="blame-body">
        {lines.map((ln, i) => {
          const prev = lines[i - 1];
          const runStart =
            !prev || prev.author_type !== ln.author_type || prev.model !== ln.model || prev.reviewed !== ln.reviewed;
          const who = ln.author_type === "human" ? "you" : ln.model || ln.agent;
          const unrev = !ln.reviewed && ln.author_type !== "human";
          return (
            <div className={`bl ${ln.author_type}`} key={i} title={ln.prompt || ""}>
              <span className="bln">{ln.line_no}</span>
              <span className="blc">{ln.content || " "}</span>
              {runStart ? (
                <span className={`who ${ln.author_type}`}>
                  {who}
                  {unrev ? <span style={{ color: "var(--warn)" }}> · unreviewed</span> : null}
                </span>
              ) : (
                <span />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
