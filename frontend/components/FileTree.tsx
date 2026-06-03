"use client";
import { useMemo, useState } from "react";

type FileStat = { path: string; lines: number; ai_lines: number; unreviewed: number };
type Node = { name: string; path: string; children: Node[]; file?: FileStat };

function buildTree(files: FileStat[]): Node {
  const root: Node = { name: "", path: "", children: [] };
  for (const f of files) {
    const parts = f.path.split("/");
    let cur = root;
    parts.forEach((part, i) => {
      const p = parts.slice(0, i + 1).join("/");
      let child = cur.children.find((c) => c.name === part);
      if (!child) {
        child = { name: part, path: p, children: [], file: i === parts.length - 1 ? f : undefined };
        cur.children.push(child);
      }
      cur = child;
    });
  }
  const sortRec = (n: Node) => {
    n.children.sort((a, b) => (b.children.length ? 1 : 0) - (a.children.length ? 1 : 0) || a.name.localeCompare(b.name));
    n.children.forEach(sortRec);
  };
  sortRec(root);
  return root;
}

function Row({ node, depth, selected, onSelect, collapsed, toggle }: any) {
  const pad = { paddingLeft: 8 + depth * 14 };
  if (node.file) {
    const f = node.file as FileStat;
    const pct = f.lines ? Math.round((100 * f.ai_lines) / f.lines) : 0;
    return (
      <div className={`trow${selected === node.path ? " active" : ""}`} style={pad} onClick={() => onSelect(node.path)}>
        <span className="caret" />
        <span className="fname">{node.name}</span>
        <span className="aibar" title={`${pct}% AI-authored`}><span style={{ width: `${pct}%` }} /></span>
        {f.unreviewed > 0 && <span className="unrev" title={`${f.unreviewed} unreviewed AI lines`} />}
      </div>
    );
  }
  const isCol = collapsed.has(node.path);
  return (
    <>
      <div className="trow" style={pad} onClick={() => toggle(node.path)}>
        <span className="caret">{isCol ? "▸" : "▾"}</span>
        <span className="fname">{node.name}/</span>
      </div>
      {!isCol && node.children.map((c: Node) => (
        <Row key={c.path} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} collapsed={collapsed} toggle={toggle} />
      ))}
    </>
  );
}

export default function FileTree({ files, selected, onSelect }: { files: FileStat[]; selected: string; onSelect: (p: string) => void }) {
  const tree = useMemo(() => buildTree(files), [files]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const toggle = (p: string) =>
    setCollapsed((s) => {
      const n = new Set(s);
      n.has(p) ? n.delete(p) : n.add(p);
      return n;
    });
  return (
    <div className="tree">
      {tree.children.map((c) => (
        <Row key={c.path} node={c} depth={0} selected={selected} onSelect={onSelect} collapsed={collapsed} toggle={toggle} />
      ))}
    </div>
  );
}
