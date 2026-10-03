# ADR 0003: The tool gateway, not the prompt, is the authority

**Status:** accepted (2026-10-03)

**Context.** Local models vary in instruction-following; imported content can carry
prompt injection; robot and guest clients must be narrower than the owner.

**Decision.** Clients authenticate with bearer tokens mapped to roles. Every tool call,
whatever its origin (model, deterministic router, UI button), passes through
`ToolGateway.call`, which checks: tool exists → enabled → client permission → Pydantic
schema (extra fields forbidden) → resource allowlist → execute with timeout → audit row.
Tool output is wrapped as untrusted before it reaches the model. The model is only ever
shown the specs it may use.

**Consequences.** A hallucinated or injected call cannot act. Permissions are testable
without a model (`ScriptedProvider`). Adding a tool means adding an args model, a handler
and a permission, nothing in the prompt.
