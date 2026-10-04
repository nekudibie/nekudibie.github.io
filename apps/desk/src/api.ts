import type { ActionItem, AttemptResult, Decision, Dependency, Doc, Entity, CameraView, Fact, Job, LessonSummary, LessonView, Me, Message, Proposal, Recording, Reminder, Schedule, SearchHit, Segment, StreamEvent } from "./types";

const LS_URL = "companion.apiUrl";
const LS_TOKEN = "companion.token";

export function getBaseUrl(): string {
  try { return localStorage.getItem(LS_URL) || window.location.origin; } catch { return window.location.origin; }
}
export function getToken(): string {
  try { return localStorage.getItem(LS_TOKEN) || ""; } catch { return ""; }
}
export function saveSettings(url: string, token: string) {
  try { localStorage.setItem(LS_URL, url.replace(/\/$/, "")); localStorage.setItem(LS_TOKEN, token.trim()); } catch { /* storage blocked */ }
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (init.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(getBaseUrl() + path, { ...init, headers });
  } catch (e) {
    throw new ApiError(0, "network", "Cannot reach the companion API");
  }
  if (!res.ok) {
    let code = "http_error", msg = res.statusText;
    try { const j = await res.json(); code = j?.error?.code || code; msg = j?.error?.message || msg; } catch { /* no body */ }
    throw new ApiError(res.status, code, msg);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  me: () => req<Me>("/v1/me"),
  ready: () => req<{ ready: boolean; dependencies: Dependency[] }>("/readyz"),
  status: () => req<{ dependencies: Dependency[]; llm: { provider: string; model: string; is_fixture: boolean }; home: { provider: string | null; is_fixture: boolean }; vault_mode: string }>("/v1/status"),
  version: () => req<{ version: string; git_sha: string | null; python: string }>("/version"),
  settings: () => req<{ config: Record<string, unknown>; warnings: string[] }>("/v1/settings"),
  conversations: () => req<{ id: string; title: string; updated_at: string; message_count: number }[]>("/v1/conversations"),
  conversation: (id: string) => req<{ conversation: { id: string; title: string }; messages: Message[] }>(`/v1/conversations/${id}`),
  newConversation: () => req<{ id: string }>("/v1/conversations", { method: "POST", body: "{}" }),
  cancel: (id: string) => req<{ cancelled_turns: number }>(`/v1/conversations/${id}/cancel`, { method: "POST" }),
  notes: () => req<Doc[]>("/v1/memory/notes?limit=100"),
  saveNote: (text: string, title: string, kind: string) => req<Doc>("/v1/memory/notes", { method: "POST", body: JSON.stringify({ text, title, kind }) }),
  search: (query: string) => req<{ hits: SearchHit[]; strategy: string }>("/v1/memory/search", { method: "POST", body: JSON.stringify({ query, limit: 10 }) }),
  document: (id: string) => req<Doc>(`/v1/memory/documents/${id}`),
  history: (id: string) => req<Doc[]>(`/v1/memory/documents/${id}/history`),
  correct: (id: string, new_text: string, reason: string) => req<Doc>(`/v1/memory/documents/${id}/correct`, { method: "POST", body: JSON.stringify({ new_text, reason }) }),
  deleteDoc: (id: string) => req<{ note: string }>(`/v1/memory/documents/${id}`, { method: "DELETE" }),
  candidates: () => req<Fact[]>("/v1/memory/facts/candidates"),
  facts: () => req<Fact[]>("/v1/memory/facts"),
  confirmFact: (id: string) => req<Fact>(`/v1/memory/facts/${id}/confirm`, { method: "POST" }),
  rejectFact: (id: string, reason = "") => req<Fact>(`/v1/memory/facts/${id}/reject`, { method: "POST", body: JSON.stringify({ reason }) }),
  retractFact: (id: string, reason = "") => req<Fact>(`/v1/memory/facts/${id}/retract`, { method: "POST", body: JSON.stringify({ reason }) }),
  updateFact: (id: string, value: string, reason = "") => req<Fact>(`/v1/memory/facts/${id}/update`, { method: "POST", body: JSON.stringify({ value, reason }) }),
  decisions: () => req<Decision[]>("/v1/memory/decisions"),
  weather: (day = "week") => req<{ ok: boolean; data: { location: string; days: { date: string; description: string; temp_max_c: number | null; temp_min_c: number | null; precipitation_probability_pct: number | null }[]; fetched_at: string; is_stale: boolean; stale_reason?: string | null; is_fixture: boolean; attribution: string } }>(`/v1/weather?day=${day}`),
  maths: (expression: string, task: string) => req<{ ok: boolean; data: { parsed: string; result: string; approx?: string | null; explanation: string; steps: string[]; method: string } }>("/v1/maths", { method: "POST", body: JSON.stringify({ expression, task }) }),
  decks: () => req<{ document_id: string; name: string; format: string; commander?: string | null; main_count: number; custom_cards: string[] }[]>("/v1/mtg/decks"),
  importDeck: (name: string, format: string, decklist: string, commander?: string) => req<unknown>("/v1/mtg/decks", { method: "POST", body: JSON.stringify({ name, format, decklist, commander: commander || null }) }),
  checkDeckCard: (id: string, card: string) => req<{ data: { legal: boolean | null; ambiguous: string[]; findings: { detail: string; ok: boolean; rule?: string | null }[]; card?: { name: string } | null; is_fixture: boolean; note: string; rules: Record<string, string> } }>(`/v1/mtg/decks/${id}/check`, { method: "POST", body: JSON.stringify({ card }) }),
  emailStatus: () => req<{ enabled: boolean; provider?: string | null; is_fixture?: boolean; account?: string; read_only?: boolean; health?: { status: string; detail: string } }>("/v1/email/status"),
  emailSearch: (query: string) => req<{ messages: { id: string; subject: string; sender: string; date?: string | null; snippet: string; link?: string | null }[]; is_fixture: boolean }>("/v1/email/search", { method: "POST", body: JSON.stringify({ query, limit: 10 }) }),
  orders: (sync: boolean) => req<unknown>(`/v1/orders?days=365&sync=${sync}`),
  deleteFixtureOrders: () => req<{ deleted: number; note: string }>("/v1/orders/fixtures", { method: "DELETE" }),
  robotStatus: () => req<{ mode: string; state: string; reason: string; pose: { x_m: number; y_m: number; theta_deg: number }; sensors: { battery_pct: number; link_ok: boolean; bumper_front: boolean; cliff_front: boolean }; estop_latched: boolean; note: string; limits: { max_linear_mps: number; max_angular_rps: number; watchdog_timeout_s: number } }>("/v1/robot/status"),
  robotAction: (action: "stop" | "estop" | "reset") => req<unknown>(`/v1/robot/${action}`, { method: "POST" }),
  robotLook: (dir: string) => req<unknown>("/v1/robot/command", { method: "POST", body: JSON.stringify({ kind: "look", look: dir }) }),
  tutorCourse: () => req<{ course: { id: string; title: string; description: string }; lessons: LessonSummary[]; summary: { lessons: number; mastered: number; needs_review: string[]; weak_topics: string[]; attempts: number } }>("/v1/tutor/course"),
  tutorNext: () => req<{ lesson: LessonView | null; reason: string }>("/v1/tutor/next"),
  tutorLesson: (id: string) => req<LessonView>(`/v1/tutor/lessons/${id}`),
  tutorAttempt: (lesson_id: string, exercise_id: string, code: string, output: string | null) => req<AttemptResult>("/v1/tutor/attempts", { method: "POST", body: JSON.stringify({ lesson_id, exercise_id, code, output: output || null }) }),
  tutorPropose: (goal: string, time_local: string) => req<{ proposals: Proposal[]; note: string }>("/v1/tutor/plan/propose", { method: "POST", body: JSON.stringify({ goal, time_local }) }),
  tutorAccept: (proposal_id: string, time_local: string) => req<{ schedule: Schedule }>("/v1/tutor/plan/accept", { method: "POST", body: JSON.stringify({ proposal_id, time_local }) }),
  tutorPlan: () => req<Schedule[]>("/v1/tutor/plan"),
  pendingReminders: () => req<Reminder[]>("/v1/reminders/pending"),
  ackReminder: (id: string) => req<Reminder>(`/v1/reminders/${id}/ack`, { method: "POST" }),
  snoozeReminder: (id: string, minutes: number) => req<Reminder>(`/v1/reminders/${id}/snooze`, { method: "POST", body: JSON.stringify({ minutes }) }),
  schedules: () => req<Schedule[]>("/v1/schedules"),
  scheduleAction: (id: string, action: "pause" | "resume" | "cancel") => req<Schedule>(`/v1/schedules/${id}/${action}`, { method: "POST" }),
  jobs: () => req<{ jobs: Job[]; counts: Record<string, number>; worker_embedded: boolean }>("/v1/jobs"),
  cancelJob: (id: string) => req<Job>(`/v1/jobs/${id}/cancel`, { method: "POST" }),
  retryJob: (id: string) => req<Job>(`/v1/jobs/${id}/retry`, { method: "POST" }),
  meetings: () => req<Recording[]>("/v1/meetings"),
  meeting: (id: string) => req<{ recording: Recording; chunks: number; segments: number; jobs: Job[]; actions: ActionItem[] }>(`/v1/meetings/${id}`),
  meetingSegments: (id: string) => req<Segment[]>(`/v1/meetings/${id}/segments`),
  startMeeting: (title: string, participants_informed: boolean, route: string) => req<Recording>("/v1/meetings", { method: "POST", body: JSON.stringify({ title, participants_informed, route }) }),
  meetingControl: (id: string, action: "pause" | "resume" | "stop" | "cancel" | "retry") => req<unknown>(`/v1/meetings/${id}/${action}`, { method: "POST" }),
  confirmAction: (meetingId: string, actionId: string, body: { owner?: string; due_at?: string }) => req<ActionItem>(`/v1/meetings/${meetingId}/actions/${actionId}/confirm`, { method: "POST", body: JSON.stringify(body) }),
  putChunk: async (id: string, seq: number, wav: Blob, sha256: string) => {
    const res = await fetch(`${getBaseUrl()}/v1/meetings/${id}/chunks/${seq}`, { method: "PUT", headers: { Authorization: `Bearer ${getToken()}`, "Content-Type": "audio/wav", "X-Content-SHA256": sha256 }, body: wav });
    if (!res.ok) { let msg = res.statusText; try { msg = (await res.json())?.error?.message || msg; } catch { /* ignore */ } throw new ApiError(res.status, "chunk", msg); }
    return res.json();
  },
  entities: () => req<Entity[]>("/v1/home/entities"),
  homeStatus: () => req<{ enabled: boolean; provider: string | null; is_fixture: boolean }>("/v1/home/status"),
  command: (entity_id: string, action: string, extra: Record<string, unknown> = {}) =>
    req<{ ok: boolean; new_state: string; is_fixture: boolean }>(`/v1/home/entities/${entity_id}/command`, { method: "POST", body: JSON.stringify({ action, ...extra }) }),
  cameras: () => req<CameraView[]>("/v1/home/cameras"),
  streamTicket: (entity_id: string) => req<{ ticket: string; expires_in_s: number; stream_url: string }>(`/v1/home/cameras/${entity_id}/stream-ticket`, { method: "POST" }),
  snapshotBlob: async (entity_id: string): Promise<{ url: string; fixture: boolean }> => {
    const res = await fetch(`${getBaseUrl()}/v1/home/cameras/${entity_id}/snapshot`, { headers: { Authorization: `Bearer ${getToken()}` } });
    if (!res.ok) throw new ApiError(res.status, "snapshot", "snapshot failed");
    return { url: URL.createObjectURL(await res.blob()), fixture: res.headers.get("x-companion-fixture") === "true" };
  },
};

/** POST a message and stream typed events. Resolves when the stream ends. */
export async function streamMessage(conversationId: string, content: string, onEvent: (e: StreamEvent) => void, signal?: AbortSignal): Promise<void> {
  const res = await fetch(`${getBaseUrl()}/v1/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ content, input_mode: "text", client_capabilities: ["screen", "camera_panel"] }),
    signal,
  });
  if (!res.ok || !res.body) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j?.error?.message || msg; } catch { /* ignore */ }
    throw new ApiError(res.status, "stream", msg);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx); buf = buf.slice(idx + 2);
      let type = "message", data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) type = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      try { onEvent({ ...(JSON.parse(data) as object), type } as StreamEvent); } catch { /* skip malformed */ }
    }
  }
}
