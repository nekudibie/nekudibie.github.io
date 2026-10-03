# ADR 0005: Vault reachable in-process or over HTTP behind one client protocol

**Status:** accepted (2026-10-03)

**Context.** One development machine today; a separate vault/home server later.

**Decision.** `VaultClient` is an async protocol with `LocalVaultClient` (direct service
calls via a thread) and `HttpVaultClient` (bearer service token; the acting client id and
memory scopes travel in `X-Companion-Actor` / `X-Companion-Scopes` headers so the vault
enforces scope and audits per actor). `vault.mode` selects the implementation.

**Consequences.** Orchestration code is identical in both modes (tested in
`tests/integration/test_remote_vault.py`). The vault trusts the API's forwarded scopes,
so the service token must be kept to the API host.
