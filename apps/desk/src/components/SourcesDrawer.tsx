import { useEffect, useState } from "react";
import { api } from "../api";
import type { Doc, Source } from "../types";
import { fmtTime } from "./Common";

export default function SourcesDrawer({ sources, onClose }: { sources: Source[]; onClose: () => void }) {
  const [open, setOpen] = useState<Doc | null>(null);
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === "Escape" && onClose(); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [onClose]);
  return (
    <aside className="drawer" aria-label="Sources">
      <div className="row" style={{ justifyContent: "space-between" }}><h2 style={{ margin: 0 }}>Sources</h2><button className="small" onClick={onClose}>Close</button></div>
      <p className="muted">These are the stored records the answer was drawn from. Anything not listed here is the model's own inference.</p>
      {sources.map((s) => (
        <div className="source" key={s.label + s.chunk_id}>
          <div><b>[{s.label}]</b> {s.title}</div>
          <div className="muted" style={{ fontSize: ".85rem" }}>{s.source_type}{s.captured_at ? ` · ${fmtTime(s.captured_at)}` : ""}{s.anchor && "start" in s.anchor ? ` · chars ${String(s.anchor.start)}–${String(s.anchor.end)}` : ""}</div>
          <p style={{ margin: "6px 0" }}>{s.snippet}</p>
          <div className="row">
            <button className="small" onClick={() => api.document(s.document_id).then(setOpen)}>Open record</button>
            {s.source_uri && <a href={s.source_uri} target="_blank" rel="noreferrer">Original link</a>}
          </div>
        </div>
      ))}
      {open && (
        <div className="card">
          <h3>{open.title} <span className="badge">rev {open.revision}</span></h3>
          <pre style={{ whiteSpace: "pre-wrap" }}>{open.text}</pre>
          <button className="small" onClick={() => setOpen(null)}>Hide</button>
        </div>
      )}
    </aside>
  );
}
