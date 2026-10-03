import { useEffect, useState } from "react";
import { api } from "../api";
import type { Message } from "../types";
import { fmtTime } from "./Common";

export default function TranscriptPanel({ onOpen }: { onOpen: (id: string) => void }) {
  const [convs, setConvs] = useState<{ id: string; title: string; updated_at: string; message_count: number }[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  useEffect(() => { api.conversations().then(setConvs).catch(() => setConvs([])); }, []);
  useEffect(() => { if (sel) api.conversation(sel).then((c) => setMsgs(c.messages)); }, [sel]);
  return (
    <div className="grid">
      <div className="card">
        <h2>Conversations</h2>
        <div className="list">{convs.map((c) => <div key={c.id} className="item" onClick={() => setSel(c.id)}><b>{c.title || "(untitled)"}</b><div className="muted" style={{ fontSize: ".8rem" }}>{fmtTime(c.updated_at)} · {c.message_count} messages</div></div>)}</div>
        {convs.length === 0 && <p className="muted">No conversations yet.</p>}
      </div>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}><h2>Transcript</h2>{sel && <button className="small" onClick={() => onOpen(sel)}>Continue in chat</button>}</div>
        {msgs.map((m) => (
          <div key={m.id} style={{ padding: "8px 0", borderTop: "1px solid var(--line)" }}>
            <div className="muted" style={{ fontSize: ".8rem" }}>{m.role} · {fmtTime(m.created_at)}{m.meta?.route ? ` · ${String(m.meta.route)}` : ""}{Array.isArray(m.meta?.tool_calls) && (m.meta.tool_calls as string[]).length ? ` · tools: ${(m.meta.tool_calls as string[]).join(", ")}` : ""}</div>
            <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
