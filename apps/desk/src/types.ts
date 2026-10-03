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

export interface Job { id: string; kind: string; status: string; priority: number; progress: number; progress_note?: string | null; error?: string | null; created_at: string; finished_at?: string | null; payload: Record<string, unknown>; attempts: number }
export interface Recording { id: string; title: string; status: string; started_at: string; stopped_at?: string | null; chunk_count: number; audio_ms: number; paused_total_ms: number; transcript_document_id?: string | null; summary_document_id?: string | null; error?: string | null; route: string }
export interface Segment { id: string; start_ms: number; end_ms: number; text: string; speaker?: string | null; confidence?: number | null }
export interface ActionItem { id: string; title: string; owner?: string | null; owner_confidence: number; due_at?: string | null; due_text?: string | null; due_confidence: number; status: string; source_quote?: string | null; meeting_id?: string | null }

export interface Reminder { id: string; schedule_id: string; due_at: string; fired_at?: string | null; status: string; title: string; body: string; kind: string; delivery_count: number; payload: Record<string, unknown> }
export interface Schedule { id: string; kind: string; title: string; body: string; timezone: string; rule: { type: string; at_local?: string; time_local?: string; days?: number[] }; next_run_at?: string | null; status: string }

export interface LessonSummary { id: string; title: string; objectives: string[]; topics: string[]; minutes: number; exercises: number; status: string; attempts: number }
export interface LessonView { id: string; title: string; objectives: string[]; explanation: string; examples: { code: string; output: string; note: string }[]; exercises: { id: string; prompt: string; starter: string; topics: string[]; hints_available: number; attempts: number; needs_output: boolean }[]; topics: string[]; references: string[]; next_steps: string; minutes: number; progress: { status: string; attempts: number; weak_topics: string[] } | null }
export interface AttemptResult { result: { passed: boolean; score: number; feedback: string[]; passed_checks: string[]; failed_checks: string[]; syntax_error?: string | null; method: string; output_checked: boolean }; progress: { status: string; attempts: number; weak_topics: string[] }; hint?: string | null; solution_notes?: string | null }
export interface Proposal { id: string; title: string; days: number[]; time_local: string; lessons_per_week: number; weeks: number; description: string }
