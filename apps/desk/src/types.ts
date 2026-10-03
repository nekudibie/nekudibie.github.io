export type AssistantState =
  | "idle" | "listening" | "transcribing" | "thinking" | "tool_running" | "speaking"
  | "muted" | "recording" | "offline" | "error";

export interface Source {
  label: string; document_id: string; chunk_id?: string; title: string; snippet: string;
  source_type: string; anchor?: Record<string, unknown>; source_uri?: string | null; captured_at?: string | null;
}

export interface ToolCallEv { call_id: string; name: string; arguments?: Record<string, unknown>; status: string; reason?: string }
export interface ToolResultEv { call_id: string; name: string; ok: boolean; summary: string; provider?: string | null; is_fixture: boolean; data: Record<string, unknown> }
export interface UIEv { action: string; payload: Record<string, unknown> }

export type StreamEvent =
  | { type: "state"; state: AssistantState; detail?: string }
  | { type: "token"; text: string }
  | ({ type: "tool_call" } & ToolCallEv)
  | ({ type: "tool_result" } & ToolResultEv)
  | ({ type: "ui" } & UIEv)
  | { type: "sources"; sources: Source[] }
  | { type: "done"; message_id: string; route: string; model?: string; usage: Record<string, unknown>; duration_ms: number }
  | { type: "error"; code: string; message: string; recoverable: boolean };

export interface Message {
  id: string; role: "user" | "assistant" | "tool" | "system"; content: string; sources: Source[];
  meta: Record<string, unknown>; created_at: string; tool_name?: string | null;
}

export interface ChatItem {
  id: string; role: "user" | "assistant"; content: string; sources: Source[];
  tools: { call: ToolCallEv; result?: ToolResultEv }[]; streaming?: boolean; error?: string; route?: string; created_at?: string;
}

export interface Entity {
  entity_id: string; domain: string; friendly_name: string; state: string; attributes: Record<string, unknown>;
  capabilities: { on_off: boolean; brightness: boolean; color_temp: boolean; rgb_color: boolean; activate: boolean; snapshot: boolean; stream: boolean };
  provider: string; is_fixture: boolean;
}

export interface CameraView { entity_id: string; friendly_name: string; snapshot_url: string; stream_kind: string; stream_url?: string | null; provider: string; is_fixture: boolean; note: string }

export interface Doc { id: string; kind: string; title: string; text: string | null; scope: string; project?: string | null; revision: number; created_at: string; deleted_at?: string | null; supersedes_id?: string | null; provenance: { source_type: string; trust: string; source_uri?: string | null } }

export interface SearchHit { document_id: string; chunk_id: string; title: string; kind: string; snippet: string; text: string; score: number; created_at: string; is_current: boolean }

export interface Dependency { name: string; status: "ok" | "degraded" | "down" | "disabled" | "fixture"; detail: string; latency_ms?: number | null }
export interface Me { client_id: string; role: string; label: string; permissions: string[]; tools: string[]; owner_name: string; timezone: string; instance: string }

export interface Fact { id: string; subject: string; predicate: string; value: string; status: string; confidence: number; trust: string; evidence_quote?: string | null; evidence_message_id?: string | null; valid_from?: string | null; created_at: string; confirmed_at?: string | null; supersedes_id?: string | null }
export interface Decision { id: string; project_name?: string | null; statement: string; rationale: string; status: string; decided_at: string; supersedes_id?: string | null }
