# Primary sources

Checked from the development container on the date shown. Several vendor sites were
blocked by the container's egress proxy, so GitHub-hosted copies of the same documents
were used where noted; anything marked *snippet* came from search-result excerpts only
and should be re-read on a normal connection before relying on fine detail.

| Topic | Source | Checked | Notes |
|---|---|---|---|
| Ollama HTTP API (`/api/chat` streaming, `tools`, `tool_name`, `/api/show` `capabilities`, `/api/tags`, `/api/version`) | https://github.com/ollama/ollama/blob/main/docs/api.md (raw) | 2026-10-03 | Adapter in `packages/integrations/companion_integrations/llm/ollama.py` |
| Ollama streaming with tool calls | https://github.com/ollama/ollama/releases/tag/v0.8.0 | 2026-10-03 | "Ollama will now stream responses with tool calls" |
| Home Assistant REST API | https://developers.home-assistant.io/docs/api/rest/ (via GitHub raw of `docs/api/rest.md`) | 2026-10-03 | `Authorization: Bearer`, `/api/states`, `/api/services/<domain>/<service>`, `/api/camera_proxy/<entity_id>` |
| Home Assistant Container install | https://www.home-assistant.io/installation/linux (via GitHub raw includes) | 2026-10-03 | No add-ons ("apps") in Container installs; `network_mode: host`, `privileged`, `/config` volume, `TZ` |
| Home Assistant Ollama integration | https://www.home-assistant.io/integrations/ollama/ (via GitHub raw) | 2026-10-03 | "Controlling Home Assistant is an experimental feature"; "Only models that support Tools may control Home Assistant" |
| Raspberry Pi OS (Debian 13 "Trixie", Python 3.13) | https://www.raspberrypi.com/software/operating-systems/ (*snippet*; site blocked) | 2026-10-03 | Current images are Trixie-based; Legacy Bookworm images still offered per snippet |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper | 2026-10-03 | MIT; CPU int8; PyPI 1.2.1; depends on CTranslate2 (aarch64 wheels on PyPI) |
| Piper TTS | https://github.com/OHF-Voice/piper1-gpl and `docs/API_PYTHON.md` | 2026-10-03 | GPL-3.0; `pip install piper-tts` (1.8.0, aarch64 wheels); `python3 -m piper.download_voices` |
| wyoming-satellite | https://github.com/rhasspy/wyoming-satellite | 2026-10-03 | Archived 27 January 2026; superseded by Linux Voice Assistant |
| Linux Voice Assistant | https://github.com/OHF-Voice/linux-voice-assistant | 2026-10-03 | Apache-2.0; ESPHome protocol to HA; openWakeWord/microWakeWord; Python 3.11/3.13; x64 + ARM64 |
| openWakeWord | https://pypi.org/project/openwakeword (0.6.0) | 2026-10-03 | Pure-Python package; Pi 3 can run many models per core (project claim, not measured here) |
| Open-Meteo API & terms | https://github.com/open-meteo/open-meteo (README) | 2026-10-03 | Free non-commercial, no key, CC BY 4.0 data, attribution link required, <10k req/day |
| Scryfall API rules | https://scryfall.com/docs/api (*snippet*; site blocked) | 2026-10-03 | `User-Agent` + `Accept` required; ≤10 req/s; cache ≥24h |
| Gmail API messages.list/get | https://developers.google.com/workspace/gmail/api (via googleapis python client docs on GitHub) | 2026-10-03 | `q`, `pageToken`, `maxResults` ≤500; `format=metadata/full`; `internalDate` |
| Gmail scopes / verification | https://developers.google.com/workspace/gmail/api/auth/scopes (*snippet*) | 2026-10-03 | `gmail.readonly` is a *restricted* scope; unverified apps limited to 100 test users |
| Google OAuth for desktop apps | https://developers.google.com/identity/protocols/oauth2/native-app (*snippet*) | 2026-10-03 | Loopback redirect + PKCE |
| PyPI versions used for the lock | https://pypi.org | 2026-10-03 | See `uv.lock`; aarch64 wheel availability checked for ctranslate2, piper-tts, onnxruntime, cryptography, numpy |
