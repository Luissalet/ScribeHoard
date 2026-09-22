"""Self-test of the capture → VAD → transcription pipeline without the web app.

    python scripts/selftest.py            # real devices: lists them, records 5 s (mic + loopback on Windows)
    python scripts/selftest.py --fake     # fixture WAV streamed by the fake backend (works anywhere)
    python scripts/selftest.py --fake --fixture path/to/speech.wav --seconds 8 --model tiny --transcriber whisper

Prints devices, chunk boundaries, live segments and timings, then the final merged transcript.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scribe.audio import select_backend  # noqa: E402
from scribe.config import Config  # noqa: E402
from scribe.db import Database  # noqa: E402
from scribe.events import EventBus  # noqa: E402
from scribe.pipeline import Pipeline  # noqa: E402
from scribe.recorder import Recorder  # noqa: E402
from scribe.settings import SettingsStore  # noqa: E402
from scribe.store import SessionStore  # noqa: E402
from scribe.transcribe import select_transcriber  # noqa: E402
from scribe.worker import TranscriptionWorker  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fake", action="store_true", help="use the fake backend (WAV fixture) instead of real devices")
    parser.add_argument("--fixture", default="", help="WAV (or mic.wav,system.wav) for the fake backend")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--transcriber", default="auto", choices=["auto", "whisper", "fake"])
    parser.add_argument("--model", default="tiny")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--no-system", action="store_true", help="microphone only")
    parser.add_argument("--data-dir", default="", help="where models/sessions go (default: a temp dir; models under <repo>/data/models)")
    args = parser.parse_args()

    config = Config.from_env()
    data_dir = Path(args.data_dir) if args.data_dir else Path(tempfile.mkdtemp(prefix="scribe-selftest-"))
    models_dir = config.models_dir  # keep downloaded models in the real data dir
    backend, notes = select_backend("fake" if args.fake else config.audio_backend, args.fixture or config.fake_fixture, config.fake_speed)
    print(f"backend: {backend.name}")
    for note in notes:
        print(f"  note: {note}")
    devices = backend.devices()
    print("microphones:", ", ".join(f"{d.name}{' (default)' if d.default else ''}" for d in devices.mic) or "none")
    print("system/loopback:", ", ".join(f"{d.name}{' (default)' if d.default else ''}" for d in devices.system) or "none")
    for note in devices.notes:
        print(f"  note: {note}")

    db = Database(data_dir / "selftest.db")
    settings = SettingsStore(db)
    store = SessionStore(db, data_dir / "sessions")
    transcriber, t_notes = select_transcriber(args.transcriber, models_dir, args.model, args.device, "auto")
    for note in t_notes:
        print(f"  note: {note}")
    print(f"transcriber: {transcriber.info()}")
    started = time.time()
    transcriber.ensure_loaded()
    print(f"model ready in {time.time() - started:.1f}s")

    bus, worker = EventBus(), TranscriptionWorker()
    worker.start()
    pipeline = Pipeline(store, transcriber, worker, bus)
    recorder = Recorder(backend, settings, store, transcriber, worker, bus)
    recorder.on_stopped = pipeline.enqueue_final

    system = not args.no_system and (args.fake or bool(devices.system))
    try:
        session = recorder.start("Selftest", "other", True, system, args.language)
    except Exception as error:
        print(f"cannot start capture: {error}")
        return 1
    sub = bus.subscribe(session["id"])
    print(f"recording {session['id']} tracks={list(recorder.current.tracks)} for {args.seconds:.0f}s …")
    deadline = time.time() + args.seconds
    while time.time() < deadline:
        time.sleep(0.25)
        while not sub.queue.empty():
            event, data = sub.queue.get_nowait()
            if event == "segment":
                print(f"  live [{data['start_s']:6.2f}-{data['end_s']:6.2f}] {data['speaker']}: {data['text']}")
        status = recorder.status()
        if status and args.fake is False:
            print(f"  levels {status['levels']}", end="\r")
    recorder.stop()
    print("stopped" + (f"; capture error: {recorder.last_error}" if recorder.last_error else ""))
    started = time.time()
    worker.wait_idle(timeout=600)
    session = store.get(session["id"])
    print(f"final pass in {time.time() - started:.1f}s → status={session['status']} duration={session['duration_s']}s error={session['error'] or '-'}")
    for seg in store.segments(session["id"]):
        print(f"  [{seg['start_s']:6.2f}-{seg['end_s']:6.2f}] {seg['speaker']}: {seg['text']}")
    info = transcriber.info()
    if info.get("last_ms") is not None:
        print(f"last transcription call: {info['last_ms']} ms")
    worker.stop()
    db.close()
    print(f"data: {data_dir}")
    return 0 if session["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
