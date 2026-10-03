import { useCallback, useState } from "react";
import CameraPanel from "./components/CameraPanel";
import Chat from "./components/Chat";
import { StateChip } from "./components/Common";
import HomePanel from "./components/HomePanel";
import NotesPanel from "./components/NotesPanel";
import ReminderBanner from "./components/ReminderBanner";
import JobsPanel from "./components/JobsPanel";
import LearnPanel from "./components/LearnPanel";
import SettingsPanel from "./components/SettingsPanel";
import SourcesDrawer from "./components/SourcesDrawer";
import ToolsPanel from "./components/ToolsPanel";
import TranscriptPanel from "./components/TranscriptPanel";
import { useClock, useConnection, useLocalState } from "./hooks";
import type { AssistantState, Source, UIEv } from "./types";

type Tab = "home" | "chat" | "notes" | "transcript" | "learn" | "jobs" | "tools" | "settings";
const TABS: { id: Tab; label: string }[] = [
  { id: "home", label: "Home" }, { id: "chat", label: "Chat" }, { id: "notes", label: "Notes" }, { id: "transcript", label: "Transcript" },
  { id: "learn", label: "Learn" }, { id: "jobs", label: "Jobs" }, { id: "tools", label: "Tools" }, { id: "settings", label: "Settings" },
];

export default function App() {
  const conn = useConnection();
  const now = useClock();
  const [tab, setTab] = useLocalState<Tab>("companion.tab", conn.phase === "unconfigured" ? "settings" : "home");
  const [conversationId, setConversationId] = useLocalState<string | null>("companion.conversation", null);
  const [state, setStateRaw] = useState<AssistantState>("idle");
  const [stateDetail, setStateDetail] = useState<string | undefined>();
  const [sources, setSources] = useState<Source[] | null>(null);
  const [camera, setCamera] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [recording, setRecording] = useState<{ active: boolean; paused: boolean }>({ active: false, paused: false });
  const [startIntent, setStartIntent] = useState<{ title: string } | null>(null);
  const [learnIntent, setLearnIntent] = useState<{ kind: string; lesson_id?: string } | null>(null);

  const setState = useCallback((s: AssistantState | ((prev: AssistantState) => AssistantState), detail?: string) => {
    setStateRaw((prev) => (typeof s === "function" ? s(prev) : s)); setStateDetail(detail);
  }, []);

  const onUIEvent = useCallback((e: UIEv) => {
    if (e.action === "show_camera") { setCamera(String(e.payload.entity_id)); setTab("home"); }
    else if (e.action === "notify") {
      if (e.payload.mute === true) setState("muted", "software mute only");
      if (e.payload.mute === false) setState("idle");
      if (e.payload.stop_speaking) setToast("Stopped.");
    } else if (e.action === "show_sources") setSources((e.payload.sources as Source[]) || []);
    else if (e.action === "open_panel") { setTab(String(e.payload.panel) as Tab); if (e.payload.intent === "start_recording") setStartIntent({ title: String(e.payload.title || "") }); if (e.payload.intent === "open_lesson" || e.payload.intent === "choose_plan") setLearnIntent({ kind: String(e.payload.intent), lesson_id: e.payload.lesson_id ? String(e.payload.lesson_id) : undefined }); }
    else if (e.action === "set_recording_indicator") setRecording({ active: !!e.payload.active, paused: !!e.payload.paused });
  }, [setState, setTab]);

  const effectiveState: AssistantState = conn.phase === "unreachable" || !conn.browserOnline ? "offline" : recording.active && state === "idle" ? "recording" : state;
  const can = (p: string) => !!conn.me?.permissions.includes(p);
  const unconfigured = conn.phase === "unconfigured" || conn.phase === "unauthorised";

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">◉ Companion</span>
        <span className="clock-small">{now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</span>
        <StateChip state={effectiveState} detail={stateDetail} />
        {conn.llmOffline && <span className="badge bad" title="Ollama is not reachable; deterministic commands still work">model offline</span>}
        {recording.active && <span className="badge bad" title="A meeting recording is in progress">● {recording.paused ? "paused" : "REC"}</span>}
        <span className="spacer" />
        <nav className="nav" aria-label="Sections">{TABS.map((t) => <button key={t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}>{t.label}</button>)}</nav>
      </header>
      <main className="main">
        {unconfigured && tab !== "settings" && (
          <div className="banner">{conn.phase === "unauthorised" ? "The saved token was rejected." : "No client token yet."} Open <button className="small" onClick={() => setTab("settings")}>Settings</button> and paste the desk token printed by dev.sh.</div>
        )}
        {conn.phase === "unreachable" && <div className="banner bad">Cannot reach the companion API at {location.origin}. The screen will keep retrying.</div>}
        {toast && <div className="banner">{toast} <button className="small" onClick={() => setToast(null)}>ok</button></div>}
        <ReminderBanner enabled={conn.phase === "ok"} />
        {tab === "home" && (
          <div className="grid">
            <div className="card">
              <div className="bigclock">{now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</div>
              <div className="bigdate">{now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</div>
              <p className="muted" style={{ marginTop: 14 }}>{conn.me ? `Signed in as ${conn.me.label || conn.me.client_id} · ${conn.me.instance}` : "Not connected"}</p>
              <div className="row" style={{ marginTop: 8 }}><button className="primary" onClick={() => setTab("chat")}>Open chat</button><button onClick={() => setTab("notes")}>Notes</button></div>
            </div>
            {conn.phase === "ok" && <CameraPanel selected={camera} setSelected={setCamera} />}
            {conn.phase === "ok" && <div style={{ gridColumn: "1 / -1" }}><HomePanel canControl={can("home.control")} onShowCamera={(id) => setCamera(id)} /></div>}
          </div>
        )}
        {tab === "chat" && conn.phase === "ok" && (
          <Chat conversationId={conversationId} setConversationId={setConversationId} llmOffline={conn.llmOffline} onUIEvent={onUIEvent} onShowSources={setSources} state={effectiveState} setState={setState} stateDetail={stateDetail} />
        )}
        {tab === "notes" && conn.phase === "ok" && <NotesPanel canWrite={can("memory.write")} canDelete={can("memory.delete")} />}
        {tab === "transcript" && conn.phase === "ok" && <TranscriptPanel onOpen={(id) => { setConversationId(id); setTab("chat"); }} />}
        {tab === "learn" && conn.phase === "ok" && <LearnPanel intent={learnIntent} />}
        {tab === "jobs" && conn.phase === "ok" && <JobsPanel canRecord={can("meeting.record")} onRecordingState={(a, p) => setRecording({ active: a, paused: p })} startIntent={startIntent} />}
        {tab === "tools" && conn.phase === "ok" && <ToolsPanel can={can} />}
        {tab === "settings" && <SettingsPanel conn={conn} />}
        {tab !== "settings" && conn.phase === "checking" && <p className="muted">Connecting…</p>}
      </main>
      {sources && <SourcesDrawer sources={sources} onClose={() => setSources(null)} />}
    </div>
  );
}
