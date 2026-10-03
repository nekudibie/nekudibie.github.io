import { useEffect, useState } from "react";
import { api } from "../api";
import type { Decision, Doc, Fact, SearchHit } from "../types";
import { ErrorLine, fmtTime } from "./Common";

export default function NotesPanel({ canWrite, canDelete }: { canWrite: boolean; canDelete: boolean }) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [text, setText] = useState(""); const [title, setTitle] = useState(""); const [kind, setKind] = useState("note");
  const [q, setQ] = useState(""); const [hits, setHits] = useState<SearchHit[] | null>(null); const [strategy, setStrategy] = useState("");
  const [open, setOpen] = useState<Doc | null>(null); const [history, setHistory] = useState<Doc[]>([]);
  const [edit, setEdit] = useState(""); const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null); const [notice, setNotice] = useState<string | null>(null);
  const [cands, setCands] = useState<Fact[]>([]); const [facts, setFacts] = useState<Fact[]>([]); const [decisions, setDecisions] = useState<Decision[]>([]);
  const [factEdit, setFactEdit] = useState<{ id: string; value: string } | null>(null);

  const load = () => {
    api.notes().then(setDocs).catch((e) => setError(e.message));
    api.candidates().then(setCands).catch(() => setCands([]));
    api.facts().then(setFacts).catch(() => setFacts([]));
    api.decisions().then(setDecisions).catch(() => setDecisions([]));
  };
  useEffect(() => { load(); }, []);
  async function factAct(fn: () => Promise<unknown>, msg: string) { try { await fn(); setNotice(msg); load(); } catch (e) { setError((e as Error).message); } }

  async function save() {
    if (!text.trim()) return;
    try { await api.saveNote(text, title, kind); setText(""); setTitle(""); setNotice("Saved."); load(); } catch (e) { setError((e as Error).message); }
  }
  async function search() {
    if (!q.trim()) { setHits(null); return; }
    try { const r = await api.search(q); setHits(r.hits); setStrategy(r.strategy); } catch (e) { setError((e as Error).message); }
  }
  async function openDoc(id: string) {
    try { const d = await api.document(id); setOpen(d); setEdit(d.text || ""); setHistory(await api.history(id)); } catch (e) { setError((e as Error).message); }
  }
  async function correct() {
    if (!open) return;
    try { const d = await api.correct(open.id, edit, reason); setNotice(`Updated to revision ${d.revision}.`); setOpen(null); load(); setHits(null); } catch (e) { setError((e as Error).message); }
  }
  async function remove() {
    if (!open || !confirm(`Delete “${open.title}”? The text and its search index entries are removed now; older backups keep it until they rotate.`)) return;
    try { const r = await api.deleteDoc(open.id); setNotice(r.note); setOpen(null); load(); setHits(null); } catch (e) { setError((e as Error).message); }
  }

  return (
    <div className="grid">
      <div className="card">
        <h2>Remember something</h2>
        <ErrorLine error={error} />
        {notice && <div className="banner">{notice} <button className="small" onClick={() => setNotice(null)}>ok</button></div>}
        <input placeholder="Title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} disabled={!canWrite} />
        <div style={{ height: 8 }} />
        <textarea placeholder="What should I remember? (a note, a decision, a fact…)" value={text} onChange={(e) => setText(e.target.value)} disabled={!canWrite} />
        <div className="row" style={{ marginTop: 8 }}>
          <select value={kind} onChange={(e) => setKind(e.target.value)} style={{ minHeight: 48, borderRadius: 12, padding: "0 12px", background: "var(--panel-2)", border: "1px solid var(--line)" }}>
            <option value="note">Note</option><option value="decision">Decision</option><option value="fact">Fact</option><option value="action">Action</option>
          </select>
          <button className="primary" onClick={save} disabled={!canWrite || !text.trim()}>Save</button>
        </div>
        {cands.length > 0 && (
          <>
            <h3 style={{ marginTop: 20 }}>Suggested facts · need your confirmation</h3>
            <p className="muted" style={{ marginTop: 0 }}>Guessed from what you said. Nothing here is used as a fact until you confirm it.</p>
            <div className="list">
              {cands.map((c) => (
                <div key={c.id} className="item" style={{ cursor: "default" }}>
                  <div><b>{c.predicate}</b>: {c.value} <span className="badge fixture">candidate</span></div>
                  {c.evidence_quote && <div className="muted" style={{ fontSize: ".85rem" }}>“{c.evidence_quote}”</div>}
                  {canWrite && <div className="row" style={{ marginTop: 6 }}>
                    <button className="small primary" onClick={() => factAct(() => api.confirmFact(c.id), "Fact confirmed.")}>Confirm</button>
                    <button className="small" onClick={() => factAct(() => api.rejectFact(c.id, "not right"), "Suggestion rejected.")}>Reject</button>
                  </div>}
                </div>
              ))}
            </div>
          </>
        )}
        <h3 style={{ marginTop: 20 }}>Search</h3>
        <div className="row">
          <input placeholder="Keywords…" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} style={{ flex: 1 }} />
          <button onClick={search}>Search</button>
        </div>
        {hits && (
          <div className="list" style={{ marginTop: 10 }}>
            {hits.length === 0 && <p className="muted">No matching records. (Honest answer: nothing stored matches those words.)</p>}
            {hits.map((h) => (
              <div key={h.chunk_id} className="item" onClick={() => openDoc(h.document_id)}>
                <div><b>{h.title}</b> <span className="badge">{h.kind}</span>{!h.is_current && <span className="badge fixture">superseded</span>}</div>
                <div className="muted" style={{ fontSize: ".9rem" }}>{h.snippet}</div>
                <div className="muted" style={{ fontSize: ".8rem" }}>{fmtTime(h.created_at)} · score {h.score.toFixed(2)} · {strategy}</div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="card">
        {open ? (
          <>
            <div className="row" style={{ justifyContent: "space-between" }}><h2>{open.title}</h2><button className="small" onClick={() => setOpen(null)}>Back</button></div>
            <dl className="kv"><dt>Kind</dt><dd>{open.kind}</dd><dt>Revision</dt><dd>{open.revision}</dd><dt>Created</dt><dd>{fmtTime(open.created_at)}</dd><dt>Source</dt><dd>{open.provenance.source_type} · {open.provenance.trust}</dd><dt>Scope</dt><dd>{open.scope}</dd></dl>
            {open.deleted_at ? <p className="banner">Deleted {fmtTime(open.deleted_at)} (tombstone).</p> : (
              <>
                <h3>Correct this record</h3>
                <textarea value={edit} onChange={(e) => setEdit(e.target.value)} disabled={!canWrite} />
                <input placeholder="Why? (e.g. that's changed)" value={reason} onChange={(e) => setReason(e.target.value)} style={{ marginTop: 8 }} disabled={!canWrite} />
                <div className="row" style={{ marginTop: 8 }}>
                  <button className="primary" onClick={correct} disabled={!canWrite || edit === open.text}>Save correction</button>
                  {canDelete && <button className="danger" onClick={remove}>Delete</button>}
                </div>
              </>
            )}
            {history.length > 1 && (<><h3 style={{ marginTop: 16 }}>History</h3><div className="list">{history.map((h) => <div key={h.id} className="item" onClick={() => openDoc(h.id)}>rev {h.revision} · {fmtTime(h.created_at)} {h.id === open.id ? "(viewing)" : ""}</div>)}</div></>)}
          </>
        ) : (
          <>
            <h2>Recent records</h2>
            <div className="list">
              {docs.length === 0 && <p className="muted">Nothing saved yet.</p>}
              {docs.map((d) => <div key={d.id} className="item" onClick={() => openDoc(d.id)}><b>{d.title}</b> <span className="badge">{d.kind}</span> <span className="muted" style={{ fontSize: ".8rem" }}>{fmtTime(d.created_at)}</span></div>)}
            </div>
            {facts.length > 0 && (<>
              <h3 style={{ marginTop: 16 }}>Confirmed facts</h3>
              <div className="list">
                {facts.map((f) => (
                  <div key={f.id} className="item" style={{ cursor: "default" }}>
                    <div><b>{f.predicate}</b>: {factEdit?.id === f.id ? <input value={factEdit.value} onChange={(e) => setFactEdit({ id: f.id, value: e.target.value })} style={{ display: "inline-block", width: "60%", minHeight: 36 }} /> : f.value}
                      <span className="badge ok" style={{ marginLeft: 6 }}>{f.trust === "owner_stated" ? "you said" : f.trust}</span>{f.supersedes_id && <span className="badge" title="an earlier value is kept in history">updated</span>}</div>
                    {canWrite && <div className="row" style={{ marginTop: 6 }}>
                      {factEdit?.id === f.id
                        ? <><button className="small primary" onClick={() => factAct(() => api.updateFact(f.id, factEdit.value, "that's changed"), "Fact updated; old value kept in history.").then(() => setFactEdit(null))}>Save</button><button className="small" onClick={() => setFactEdit(null)}>Cancel</button></>
                        : <><button className="small" onClick={() => setFactEdit({ id: f.id, value: f.value })}>That's changed</button><button className="small danger" onClick={() => factAct(() => api.retractFact(f.id, "no longer true"), "Fact retracted.")}>Retract</button></>}
                    </div>}
                  </div>
                ))}
              </div>
            </>)}
            {decisions.length > 0 && (<>
              <h3 style={{ marginTop: 16 }}>Current decisions</h3>
              <div className="list">{decisions.map((d) => <div key={d.id} className="item" style={{ cursor: "default" }}><b>{d.project_name || "No project"}</b>: {d.statement} <span className="muted" style={{ fontSize: ".8rem" }}>{fmtTime(d.decided_at)}</span>{d.supersedes_id && <span className="badge">revised</span>}</div>)}</div>
            </>)}
          </>
        )}
      </div>
    </div>
  );
}
