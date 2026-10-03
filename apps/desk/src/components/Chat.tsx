import { useEffect, useRef, useState } from "react";
import { api, ApiError, streamMessage } from "../api";
import type { AssistantState, ChatItem, Source, StreamEvent, UIEv } from "../types";
import { StateChip } from "./Common";

interface Props {
  conversationId: string | null;
  setConversationId: (id: string) => void;
  llmOffline: boolean;
  onUIEvent: (e: UIEv) => void;
  onShowSources: (s: Source[]) => void;
  state: AssistantState;
  setState: (s: AssistantState | ((prev: AssistantState) => AssistantState), detail?: string) => void;
  stateDetail?: string;
}

const QUICK = ["What time is it?", "Turn on the desk lamp", "Set study lighting", "Show the front door camera", "What did we decide about the Lantern project?"];

export default function Chat({ conversationId, setConversationId, llmOffline, onUIEvent, onShowSources, state, setState, stateDetail }: Props) {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!conversationId) { setItems([]); return; }
    api.conversation(conversationId).then((c) => {
      setItems(c.messages.filter((m) => m.role === "user" || m.role === "assistant").map((m) => ({
        id: m.id, role: m.role as "user" | "assistant", content: m.content, sources: m.sources, tools: [],
        error: typeof m.meta?.error === "string" ? String(m.meta.error) : undefined, route: m.meta?.route as string | undefined, created_at: m.created_at,
      })));
    }).catch((e) => setError(e.message));
  }, [conversationId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [items]);

  async function ensureConversation(): Promise<string> {
    if (conversationId) return conversationId;
    const c = await api.newConversation();
    setConversationId(c.id);
    return c.id;
  }

  async function send(content: string) {
    const trimmed = content.trim();
    if (!trimmed || busy) return;
    setError(null); setText(""); setBusy(true);
    const userItem: ChatItem = { id: `u-${Date.now()}`, role: "user", content: trimmed, sources: [], tools: [] };
    const asst: ChatItem = { id: `a-${Date.now()}`, role: "assistant", content: "", sources: [], tools: [], streaming: true };
    setItems((prev) => [...prev, userItem, asst]);
    const update = (fn: (a: ChatItem) => ChatItem) => setItems((prev) => prev.map((it) => (it.id === asst.id ? fn(it) : it)));
    const ctl = new AbortController(); abortRef.current = ctl;
    try {
      const cid = await ensureConversation();
      setState("thinking");
      await streamMessage(cid, trimmed, (ev: StreamEvent) => {
        switch (ev.type) {
          case "state": setState(ev.state, ev.detail); break;
          case "token": update((a) => ({ ...a, content: a.content + ev.text })); break;
          case "tool_call": update((a) => ({ ...a, tools: [...a.tools, { call: ev }] })); break;
          case "tool_result": update((a) => ({ ...a, tools: a.tools.map((t) => (t.call.call_id === ev.call_id ? { ...t, result: ev } : t)) })); break;
          case "ui": onUIEvent(ev); break;
          case "sources": update((a) => ({ ...a, sources: ev.sources })); break;
          case "error": update((a) => ({ ...a, error: ev.message })); break;
          case "done": update((a) => ({ ...a, streaming: false, route: ev.route })); break;
        }
      }, ctl.signal);
    } catch (e) {
      const msg = e instanceof DOMException && e.name === "AbortError" ? "Stopped." : (e as ApiError).message || String(e);
      update((a) => ({ ...a, error: msg, streaming: false }));
      if (!(e instanceof DOMException)) setState("error", msg);
    } finally {
      update((a) => ({ ...a, streaming: false }));
      setBusy(false); abortRef.current = null;
      setState((s) => (s === "thinking" || s === "tool_running" ? "idle" : s) as AssistantState);
      inputRef.current?.focus();
    }
  }

  async function stop() {
    abortRef.current?.abort();
    if (conversationId) { try { await api.cancel(conversationId); } catch { /* best effort */ } }
    setState("idle");
  }

  function renderContent(a: ChatItem) {
    const parts = a.content.split(/(\[S\d+\])/g);
    return parts.map((p, i) => /^\[S\d+\]$/.test(p)
      ? <span key={i} className="cite" onClick={() => onShowSources(a.sources)} role="button" title="Open sources">{p}</span>
      : <span key={i}>{p}</span>);
  }

  return (
    <div className="chat">
      <div className="messages" aria-live="polite">
        {items.length === 0 && (
          <div className="card">
            <h2>Talk to your companion</h2>
            <p className="muted">Type below. Try one of these:</p>
            <div className="row">{QUICK.map((q) => <button key={q} className="small" onClick={() => send(q)}>{q}</button>)}</div>
            {llmOffline && <p className="banner">The language model is offline. Time, lights, scenes, camera and stop still work.</p>}
          </div>
        )}
        {items.map((m) => (
          <div key={m.id} className={`msg ${m.role} ${m.error ? "error" : ""}`}>
            {m.role === "assistant" ? renderContent(m) : m.content}
            {m.streaming && !m.content && <span className="caret" />}
            {m.streaming && m.content && <span className="caret" />}
            {m.error && <div className="muted" style={{ marginTop: 6 }}>⚠ {m.error}</div>}
            {m.tools.length > 0 && (
              <div className="tools">
                {m.tools.map((t) => {
                  const cls = t.result ? (t.result.ok ? "ok" : "failed") : t.call.status === "validated" ? "" : t.call.status;
                  const label = t.result ? `${t.call.name}: ${t.result.summary}` : `${t.call.name}: ${t.call.status}${t.call.reason ? ` (${t.call.reason})` : ""}`;
                  return <span key={t.call.call_id} className={`tool ${cls}`} title={label}>{t.result?.is_fixture ? "⚠ " : ""}{label}</span>;
                })}
              </div>
            )}
            {m.sources.length > 0 && <div style={{ marginTop: 6 }}><button className="small" onClick={() => onShowSources(m.sources)}>Sources ({m.sources.length})</button></div>}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div>
        <div className="row" style={{ marginBottom: 8 }}>
          <StateChip state={state} detail={stateDetail} />
          {llmOffline && <span className="badge bad">model offline · basic commands only</span>}
          {error && <span className="badge bad">{error}</span>}
        </div>
        <div className="composer">
          <textarea ref={inputRef} value={text} placeholder="Ask, tell, or command… (Enter to send, Shift+Enter for a new line, Esc to stop)" onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } if (e.key === "Escape") stop(); }} />
          <button className="ptt" disabled title="Push-to-talk arrives with the voice milestone (native audio client). Not available in the browser without HTTPS.">🎙</button>
          <button className="stop" onClick={stop} disabled={!busy && state !== "speaking"} title="Stop speaking / cancel">■ Stop</button>
          <button className="primary" onClick={() => send(text)} disabled={busy || !text.trim()}>Send</button>
        </div>
      </div>
    </div>
  );
}
