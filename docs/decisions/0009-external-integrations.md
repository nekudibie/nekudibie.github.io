# ADR 0009: External integrations are explicit, read-only and provenance-labelled

**Status:** accepted (2026-10-03)

**Context.** Weather, card data and email need outside services; the rest of the system is
local. Users must be able to tell where an answer came from and whether it is current.

**Decision.**
* Each integration is a provider behind a protocol with a labelled fixture; `disabled` is a
  first-class setting and the tool is reported as disabled rather than silently missing.
* Open-Meteo (no key, CC BY 4.0, attribution shown), Scryfall (required headers, paced,
  24-hour cache) and Gmail (read-only scope only, PKCE loopback consent, encrypted tokens)
  are the only external calls; none is a model provider.
* Answers carry fetch time and staleness (weather), data provenance and rule citations
  (cards), and message links with payment details redacted (email). Email bodies are
  wrapped as untrusted data like every other tool result.
* Orders are derived records: statuses only move forward (confirmed → shipped → delivered)
  and refund/cancel are terminal; a confirmation is never reported as a delivery.

**Consequences.** Clear switches per integration; no cloud dependency sneaks in; the
model cannot act on anything an email says because it never had the permission to begin with.
