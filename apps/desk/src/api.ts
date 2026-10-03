import type { Decision, Dependency, Doc, Entity, CameraView, Fact, Me, Message, SearchHit, StreamEvent } from "./types";

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
