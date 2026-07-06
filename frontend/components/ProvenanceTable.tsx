export default function ProvenanceTable({ records }: { records: any[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>file</th><th>lines</th><th>author</th><th>model / agent</th>
            <th>human edit</th><th>reviewed</th><th>commit</th>
          </tr>
        </thead>
        <tbody>
          {records.slice(0, 40).map((r, i) => {
            const tone = r.author_type === "human" ? "human" : r.author_type === "hybrid" ? "hybrid" : "ai";
            const edit = Math.round((r.human_edit_ratio ?? 0) * 100);
            return (
              <tr key={`${r.file_path}:${r.lines}:${r.commit_sha ?? i}`}>
                <td><span className="file">{r.file_path}</span></td>
                <td className="mono">{r.lines}</td>
                <td><span className={`pill ${tone}`}><span className="dot" />{r.author_type}</span></td>
                <td className="mono">{r.model ?? r.agent}</td>
                <td><span className="edit-bar"><span style={{ width: `${edit}%` }} /></span>{edit}%</td>
                <td>
                  {r.reviewed
                    ? <span className="pill human"><span className="dot" />yes</span>
                    : <span className="pill warn"><span className="dot" />no</span>}
                </td>
                <td className="mono dim">{r.commit_sha}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
