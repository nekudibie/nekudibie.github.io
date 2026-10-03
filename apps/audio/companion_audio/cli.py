"""``companion-audio``: the desk's native voice client.

Keyboard control (development): Enter starts/stops a push-to-talk recording, ``s`` stops
speech, ``m`` toggles the software mute, ``q`` quits. On the Pi a GPIO button can call the
same ``press_ptt``/``release_ptt`` methods (see docs/BUILD_GUIDE.md).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from companion_core.envfile import load_env_file
from companion_core.logging import configure_logging, get_logger
from companion_core.version import repo_root

from .backends import AplayPlayback, ArecordCapture, FileCapture, NullPlayback
from .client import AudioClient, ClientConfig
from .wakeword import build_detector

log = get_logger("companion_audio")
STATE_FILE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "companion" / "audio.json"


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save_state(data: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data))


def _print_state(state: str, detail: str) -> None:
    marker = {"listening": "●", "speaking": "▶", "muted": "✕", "offline": "!", "error": "!"}.get(state, "·")
    print(f"\r[{marker} {state}{' · ' + detail if detail else ''}]".ljust(80), end="\n" if state in {"idle", "offline", "error"} else "", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="companion-audio", description="Native push-to-talk voice client")
    parser.add_argument("--api", default=os.environ.get("COMPANION_API_URL", "http://127.0.0.1:8710"))
    parser.add_argument("--token-env", default="COMPANION_DESK_TOKEN", help="env var holding this client's token")
    parser.add_argument("--input", choices=["arecord", "file"], default="arecord")
    parser.add_argument("--input-device", help="ALSA device, e.g. plughw:1,0 (see `arecord -l`)")
    parser.add_argument("--output", choices=["aplay", "null"], default="aplay")
    parser.add_argument("--output-device", help="ALSA device, e.g. plughw:0,0 (see `aplay -l`)")
    parser.add_argument("--simulate", type=Path, help="send this 16 kHz mono WAV as one utterance and exit")
    parser.add_argument("--wake-word", choices=["off", "openwakeword"], default="off")
    parser.add_argument("--wake-model", default="hey_jarvis")
    parser.add_argument("--wake-threshold", type=float, default=0.6)
    parser.add_argument("--no-speak", action="store_true", help="print replies, do not play TTS")
    parser.add_argument("--new-conversation", action="store_true")
    parser.add_argument("--record-meeting", metavar="TITLE", help="record a meeting in 20 s chunks (Enter stops); requires --participants-informed")
    parser.add_argument("--participants-informed", action="store_true", help="confirm everyone present knows the meeting is being recorded")
    parser.add_argument("--route", choices=["personal", "employer_approved"], default="personal")
    parser.add_argument("--chunk-seconds", type=float, default=20.0)
    args = parser.parse_args(argv)

    load_env_file(repo_root() / ".env")
    configure_logging("WARNING", "text")
    token = os.environ.get(args.token_env, "")
    if not token:
        print(f"error: {args.token_env} is not set (put the desk token in .env or the environment)", file=sys.stderr)
        return 2

    saved = _load_state()
    cfg = ClientConfig(api_url=args.api, token=token, conversation_id=None if args.new_conversation else saved.get("conversation_id"), speak_replies=not args.no_speak)
    if args.wake_word != "off":
        cfg.wake_word = build_detector(args.wake_word, args.wake_model, args.wake_threshold)
        cfg.wake_threshold = args.wake_threshold
    capture = FileCapture(args.simulate) if args.simulate else (FileCapture(Path("/dev/null")) if args.input == "file" else ArecordCapture(args.input_device))
    playback = NullPlayback() if args.output == "null" else AplayPlayback(args.output_device)
    client = AudioClient(cfg, capture, playback, on_state=_print_state)
    print(f"companion-audio · api {args.api} · in: {capture.describe()} · out: {playback.describe()} · wake word: {args.wake_word}")
    print("Software mute here is not a hardware microphone cut. Use a device with a physical mute switch for that.")

    async def run() -> int:
        try:
            if args.record_meeting is not None:
                if not args.participants_informed:
                    print("error: add --participants-informed once everyone present has been told. Recording refused.", file=sys.stderr)
                    return 2
                from .meeting import MeetingUploader

                up = MeetingUploader(args.api, token, capture, chunk_seconds=args.chunk_seconds)
                rid = await up.start(args.record_meeting, participants_informed=True, route=args.route)
                print(f"● RECORDING {rid} ({args.record_meeting}). Press Enter to stop.")
                loop = asyncio.get_running_loop()
                task = asyncio.create_task(up.run())
                if not args.simulate:
                    await loop.run_in_executor(None, sys.stdin.readline)
                    up.request_stop()
                stats = await task
                await up.aclose()
                print(f"stopped: {stats.chunks_sent} chunk(s), {stats.bytes_sent} bytes, {stats.retries} retries. Transcription is queued on the brain.")
                return 0
            if args.simulate:
                client.press_ptt()
                client.release_ptt()
                res = await client.ptt_turn()
                print(f"\nheard:  {res.transcript!r}{' (fixture STT)' if res.is_fixture_stt else ''}\nreply:  {res.reply}\nroute:  {res.route}\nerror:  {res.error}")
                _save_state({"conversation_id": cfg.conversation_id})
                return 0 if not res.error else 1
            if cfg.wake_word is not None:
                print("listening for the wake word (Ctrl-C to quit)")
                await client.wake_loop()
                return 0
            print("Enter = start/stop talking, s = stop speaking, m = mute toggle, q = quit")
            loop = asyncio.get_running_loop()
            recording: asyncio.Task | None = None

            async def reminder_poll() -> None:
                while True:
                    await asyncio.sleep(15)
                    try:
                        await client.announce_reminders()
                    except Exception:  # noqa: BLE001 - never let a reminder poll kill the client
                        log.exception("reminder poll failed")

            poller = asyncio.create_task(reminder_poll())
            while True:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                cmd = line.strip().lower()
                if cmd == "q" or line == "":
                    break
                if cmd == "s":
                    client.stop_speaking()
                elif cmd == "m":
                    client.toggle_mute()
                elif recording is None:
                    client.press_ptt()
                    recording = asyncio.create_task(client.ptt_turn())
                else:
                    client.release_ptt()
                    res = await recording
                    recording = None
                    print(f"\nheard: {res.transcript!r}\nreply: {res.reply}" + (f"\nerror: {res.error}" if res.error else ""))
                    _save_state({"conversation_id": cfg.conversation_id})
            poller.cancel()
            return 0
        finally:
            await client.aclose()

    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
