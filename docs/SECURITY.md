# Security model

## Principles
1. **Local-first.** No cloud LLM or cloud audio path exists in the codebase; there is
   nothing to "fall back" to. External integrations (Open-Meteo, Scryfall, Gmail) are
   explicit, feature-flagged and read-only.
2. **The model has no authority.** Clients authenticate; roles fix permissions; the tool
   gateway checks permission, schema and resource allowlists on every call. The model
   only sees tool specs it may use, and even a forged call for another tool is refused.
3. **Everything imported is data.** Notes, emails, OCR, web and tool output are wrapped in
   `<<<untrusted ...>>>` markers (look-alike markers inside are neutralised) and the system
   prompt says to treat them as data. This is defence in depth; the gateway is the control.
4. **Least privilege per client.** `rover` and `guest` roles cannot write memory, control
   the home, or view cameras. Per-client entity allowlists narrow further.
5. **No general-purpose tools.** There is no shell, eval, filesystem or Docker-socket tool
   exposed to the model, and none is planned.

## Credentials
* Tokens are random (`companion-api make-token`), presented as bearer tokens, stored only
  as SHA-256 in memory, and compared in constant time.
* All secrets come from environment variables (`.env`, mode 600, never committed).
* Home Assistant and camera credentials stay on the API host; the UI proxies through
  `/v1/home/cameras/{id}/snapshot` with its own token.
* OAuth refresh tokens (email, Milestone 7) are encrypted at rest with
  `COMPANION_TOKEN_KEY`; see docs/OPERATIONS.md.

## Logging
* JSON lines with request id and client id; bearer tokens, `token=`/`secret=` pairs and
  registered secret values are redacted by the formatter.
* Application code never logs message bodies, note text, transcripts or email content.
  Tool audit rows in `brain.db` keep arguments (truncated) because the database is private
  local data, not a log stream.

## Network
* Default bind is `127.0.0.1`. Binding to the LAN requires TLS termination or a
  firewall/VPN; see docs/OPERATIONS.md "Secure access". Browser microphone capture
  needs a secure context (HTTPS or localhost), which is one reason the native audio
  client exists.
* Service-to-service calls (API → vault, API → Home Assistant, API → Ollama) use
  bearer tokens and explicit timeouts. Nothing is exposed to the internet.

## Known gaps (tracked in docs/STATUS.md)
* Token revocation is by editing `.env`/config and restarting; a database-backed token
  table with revocation is planned.
* No rate limiting yet.
* The found USB stick stays out of every deployment (firmware cannot be certified by a scan).
