import type { AssistantState, Dependency } from "../types";

export const STATE_LABEL: Record<AssistantState, string> = {
  idle: "Idle", listening: "Listening", transcribing: "Transcribing", thinking: "Thinking", tool_running: "Working",
  speaking: "Speaking", muted: "Muted", recording: "Recording", offline: "Offline", error: "Error",
};

export function StateChip({ state, detail }: { state: AssistantState; detail?: string }) {
  return (
    <span className={`state-chip ${state}`} title={detail || ""} aria-live="polite">
      <span className="dot" /> {STATE_LABEL[state]}{detail && state !== "idle" ? ` · ${detail}` : ""}
    </span>
  );
}

export function FixtureBadge({ show, text = "Fixture · not real hardware" }: { show: boolean; text?: string }) {
  return show ? <span className="badge fixture">⚠ {text}</span> : null;
}

export function DepBadge({ d }: { d: Dependency }) {
  const cls = d.status === "ok" ? "ok" : d.status === "fixture" ? "fixture" : d.status === "down" ? "bad" : d.status === "degraded" ? "fixture" : "";
  return <span className={`badge ${cls}`} title={d.detail}>{d.name}: {d.status}</span>;
}

export function ErrorLine({ error }: { error: string | null }) {
  return error ? <div className="banner bad" role="alert">{error}</div> : null;
}

export function fmtTime(iso: string) {
  try { return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }); } catch { return iso; }
}
