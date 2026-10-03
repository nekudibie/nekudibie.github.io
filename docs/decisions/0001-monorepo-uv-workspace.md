# ADR 0001: uv workspace monorepo with one lockfile

**Status:** accepted (2026-10-03)

**Context.** Three deployment roles share schemas and infrastructure but must be
installable separately on hosts with different CPUs (x86_64 brain, aarch64 Pi).

**Decision.** One repository, a uv workspace (`[tool.uv.workspace]`) with a member per
app/package and a single `uv.lock`. Role hosts run `uv sync --package companion-<role>`;
development runs `uv sync --all-packages`. `requires-python >= 3.11` covers Raspberry
Pi OS Bookworm (3.11), Ubuntu 24.04 (3.12) and Pi OS Trixie (3.13).

**Consequences.** Shared code changes are atomic across roles. Each member needs a tiny
`pyproject.toml`. Heavy optional dependencies (faster-whisper, piper) will be extras so a
Pi desk install stays small.
