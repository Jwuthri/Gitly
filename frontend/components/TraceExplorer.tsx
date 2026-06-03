"use client";
import { useEffect, useState } from "react";

import BlameView from "@/components/BlameView";
import FileTree from "@/components/FileTree";
import { getTraceFile, getTraceTree } from "@/lib/clientApi";

export default function TraceExplorer({ repo }: { repo: string }) {
  const [files, setFiles] = useState<any[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [blame, setBlame] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    getTraceTree(repo)
      .then((d) => {
        if (!alive) return;
        setFiles(d.files || []);
        if (d.files?.length) setSelected(d.files[0].path);
      })
      .catch((e) => alive && setErr(e?.message || "failed"));
    return () => { alive = false; };
  }, [repo]);

  useEffect(() => {
    if (!selected) return;
    let alive = true;
    setBlame(null);
    getTraceFile(repo, selected)
      .then((d) => alive && setBlame(d))
      .catch((e) => alive && setErr(e?.message || "failed"));
    return () => { alive = false; };
  }, [repo, selected]);

  if (err) return <div className="callout danger"><span>{err}. Is the backend running on :8000?</span></div>;
  if (!files.length) return <div className="card dim">No files with provenance yet — run <span className="mono">make seed</span>.</div>;

  return (
    <div className="explorer">
      <FileTree files={files} selected={selected} onSelect={setSelected} />
      {blame ? <BlameView path={blame.path} lines={blame.lines} /> : <div className="card dim">loading…</div>}
    </div>
  );
}
