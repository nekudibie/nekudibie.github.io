import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { MeetingRecorder } from "../recorder";
import type { ActionItem, Job, Recording, Segment } from "../types";
import { ErrorLine, fmtTime } from "./Common";

function mmss(ms: number) { const s = Math.floor(ms / 1000); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }

export default function JobsPanel({ canRecord, onRecordingState, startIntent }: { canRecord: boolean; onRecordingState: (active: boolean, paused: boolean) => void; startIntent?: { title: string } | null }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [meetings, setMeetings] = useState<Recording[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState(startIntent?.title || "");
  const [consent, setConsent] = useState(false);
  const [route, setRoute] = useState("personal");
  const [active, setActive] = useState<Recording | null>(null);
  const [open, setOpen] = useState<{ recording: Recording; segments: Segment[]; actions: ActionItem[]; jobs: Job[] } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const recorder = useRef<MeetingRecorder | null>(null);
  const [uploaded, setUploaded] = useState(0);

  const load = () => {
    api.jobs().then((j) => setJobs(j.jobs)).catch((e) => setError(e.message));
    api.meetings().then((m) => { setMeetings(m); const a = m.find((r) => r.status === "recording" || r.status === "paused") || null; setActive(a); onRecordingState(!!a, a?.status === "paused"); }).catch(() => undefined);
  };
  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); }, []); // eslint-disable-line
  useEffect(() => { if (startIntent?.title) setTitle(startIntent.title); }, [startIntent]);

  async function start() {
    setError(null);
    if (!consent) { setError("Tick the box to confirm everyone present knows this is being recorded."); return; }
    try {
      const rec = await api.startMeeting(title, true, route);
      setActive(rec); onRecordingState(true, false); setNotice("Recording. The indicator stays on until you stop.");
      if (MeetingRecorder.supported()) {
        recorder.current = new MeetingRecorder(rec.id, 20, () => setUploaded((n) => n + 1));
        await recorder.current.start();
      } else {
        setNotice("Recording session opened. This browser cannot capture audio (needs HTTPS or localhost); send audio from the desk client: companion-audio record-meeting " + rec.id);
      }
      load();
    } catch (e) { setError((e as Error).message); }
  }
  async function control(action: "pause" | "resume" | "stop" | "cancel") {
    if (!active) return;
    try {
      if (action === "pause") recorder.current?.pause();
      if (action === "resume") recorder.current?.resume();
      if (action === "stop" || action === "cancel") { await recorder.current?.stop(); recorder.current = null; }
      await api.meetingControl(active.id, action);
      if (action === "stop") setNotice("Stopped. Transcription is queued; progress appears below.");
      load();
    } catch (e) { setError((e as Error).message); }
  }
  async function view(id: string) {
    try { const m = await api.meeting(id); const segs = await api.meetingSegments(id); setOpen({ recording: m.recording, segments: segs, actions: m.actions, jobs: m.jobs }); } catch (e) { setError((e as Error).message); }
  }
  async function confirmDraft(a: ActionItem) {
    if (!open) return;
    const owner = prompt("Owner (leave blank if unknown):", a.owner || "") ?? undefined;
    const due = prompt("Due date YYYY-MM-DD (leave blank if none):", a.due_at || "") ?? undefined;
    try { await api.confirmAction(open.recording.id, a.id, { owner: owner || undefined, due_at: due || undefined }); await view(open.recording.id); } catch (e) { setError((e as Error).message); }
  }

  return (
    <div className="grid">
      <div className="card">
        <h2>Record a meeting</h2>
        <ErrorLine error={error} />
        {notice && <div className="banner">{notice} <button className="small" onClick={() => setNotice(null)}>ok</button></div>}
        {active ? (
          <>
            <p><span className="badge bad">● {active.status === "paused" ? "PAUSED" : "RECORDING"}</span> {active.title || "(untitled)"} · {mmss(active.audio_ms)} received · {active.chunk_count} chunks{recorder.current ? ` · ${uploaded} uploaded from this browser` : ""}</p>
            <div className="row">
              {active.status === "recording" ? <button onClick={() => control("pause")}>Pause</button> : <button onClick={() => control("resume")}>Resume</button>}
              <button className="primary" onClick={() => control("stop")}>Stop &amp; transcribe</button>
              <button className="danger" onClick={() => { if (window.confirm("Discard this recording?")) control("cancel"); }}>Discard</button>
            </div>
          </>
        ) : (
          <>
            <input placeholder="Meeting title" value={title} onChange={(e) => setTitle(e.target.value)} disabled={!canRecord} />
            <label className="row" style={{ marginTop: 10 }}><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} style={{ width: 22, height: 22, minHeight: 22 }} /> Everyone present knows this meeting is being recorded.</label>
            <label className="row" style={{ marginTop: 6 }}>Material: <select value={route} onChange={(e) => setRoute(e.target.value)} style={{ minHeight: 40, borderRadius: 10, padding: "0 10px", background: "var(--panel-2)", border: "1px solid var(--line)" }}><option value="personal">Personal</option><option value="employer_approved">Employer material (approved route)</option></select></label>
            <div className="row" style={{ marginTop: 10 }}><button className="primary" onClick={start} disabled={!canRecord || !consent}>● Start recording</button>
              {!MeetingRecorder.supported() && <span className="muted">This browser cannot capture audio here (needs HTTPS/localhost); the desk client can.</span>}</div>
          </>
        )}
        <h3 style={{ marginTop: 20 }}>Jobs</h3>
        <div className="list">
          {jobs.length === 0 && <p className="muted">No jobs yet.</p>}
          {jobs.map((j) => (
            <div key={j.id} className="item" style={{ cursor: "default" }}>
              <div><b>{j.kind}</b> <span className={`badge ${j.status === "succeeded" ? "ok" : j.status === "failed" ? "bad" : j.status === "running" ? "info" : ""}`}>{j.status}</span> <span className="muted" style={{ fontSize: ".8rem" }}>{fmtTime(j.created_at)} · attempt {j.attempts}</span></div>
              {j.status === "running" && <progress value={j.progress} max={1} style={{ width: "100%" }} />}
              <div className="muted" style={{ fontSize: ".85rem" }}>{j.progress_note || j.error || ""}</div>
              <div className="row" style={{ marginTop: 4 }}>
                {(j.status === "queued" || j.status === "running") && <button className="small" onClick={() => api.cancelJob(j.id).then(load)}>Cancel</button>}
                {(j.status === "failed" || j.status === "cancelled") && <button className="small" onClick={() => api.retryJob(j.id).then(load)}>Retry</button>}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="card">
        {open ? (
          <>
            <div className="row" style={{ justifyContent: "space-between" }}><h2>{open.recording.title || "(untitled)"}</h2><button className="small" onClick={() => setOpen(null)}>Back</button></div>
            <p className="muted">{fmtTime(open.recording.started_at)} · {mmss(open.recording.audio_ms)} · status {open.recording.status}{open.recording.error ? ` · ${open.recording.error}` : ""}</p>
            <h3>Draft actions</h3>
            {open.actions.length === 0 && <p className="muted">None extracted.</p>}
            {open.actions.map((a) => (
              <div key={a.id} className="item" style={{ cursor: "default" }}>
                <div><b>{a.title}</b> <span className={`badge ${a.status === "open" ? "ok" : a.status === "done" ? "ok" : "fixture"}`}>{a.status}</span></div>
                <div className="muted" style={{ fontSize: ".85rem" }}>Owner: {a.owner || "not stated"} · Due: {a.due_text || a.due_at || "not stated"}{a.due_text && a.due_confidence < 0.5 ? " (uncertain)" : ""}</div>
                {a.source_quote && <div className="muted" style={{ fontSize: ".85rem" }}>“{a.source_quote}”</div>}
                {a.status === "draft" && canRecord && <button className="small primary" style={{ marginTop: 4 }} onClick={() => confirmDraft(a)}>Confirm as a real action</button>}
              </div>
            ))}
            <h3 style={{ marginTop: 16 }}>Transcript</h3>
            <div style={{ maxHeight: 360, overflow: "auto" }}>
              {open.segments.length === 0 && <p className="muted">No transcript yet.</p>}
              {open.segments.map((s) => <div key={s.id} style={{ padding: "4px 0" }}><span className="muted" style={{ fontSize: ".8rem" }}>[{mmss(s.start_ms)}]</span> {s.speaker ? <b>{s.speaker}: </b> : null}{s.text}</div>)}
            </div>
            <p className="muted" style={{ fontSize: ".8rem" }}>Speakers are not labelled: no diarisation has run, so none is invented.</p>
          </>
        ) : (
          <>
            <h2>Meetings</h2>
            <div className="list">
              {meetings.length === 0 && <p className="muted">No recordings yet.</p>}
              {meetings.map((m) => <div key={m.id} className="item" onClick={() => view(m.id)}><b>{m.title || "(untitled)"}</b> <span className="badge">{m.status}</span> <span className="muted" style={{ fontSize: ".8rem" }}>{fmtTime(m.started_at)} · {mmss(m.audio_ms)}</span></div>)}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
