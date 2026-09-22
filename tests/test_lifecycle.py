"""start → live segments arrive → stop → final segments replace the live ones (fake capture + fake transcriber)."""

from conftest import wait_for

from scribe.audio.wav import read_wav


def test_recording_lifecycle_two_tracks(services):
    svc = services
    sub = svc.bus.subscribe("*")  # placeholder so the bus has a subscriber map entry
    session = svc.recorder.start("Prueba", "meeting", mic=True, system=True, language="es")
    assert session["status"] == "recording" and session["sources"] == {"mic": True, "system": True}
    assert svc.recorder.status()["session_id"] == session["id"]
    live = wait_for(lambda: [s for s in svc.sessions.segments(session["id"]) if s["live"]] or None)
    assert live and {s["speaker"] for s in live} <= {"yo", "otros"}
    # the fixture plays at speed 0: wait until both tracks were consumed, then stop
    wait_for(lambda: svc.recorder.current and svc.recorder.current.elapsed >= 15.9)
    stopped = svc.recorder.stop()
    assert stopped["status"] == "processing" and stopped["duration_s"] >= 15.9
    assert svc.recorder.current is None
    assert svc.worker.wait_idle(30)
    final = svc.sessions.get(session["id"])
    assert final["status"] == "done" and final["error"] == ""
    segments = svc.sessions.segments(session["id"])
    assert segments and all(not s["live"] for s in segments)
    speakers = {s["speaker"] for s in segments}
    assert speakers == {"yo", "otros"}
    # channel = speaker: everything from the mic track is 'yo', the system track 'otros'
    folder = svc.sessions.session_dir(session["id"])
    assert (folder / "mic.wav").is_file() and (folder / "system.wav").is_file() and (folder / "audio.wav").is_file()
    mixed, _ = read_wav(folder / "audio.wav")
    assert abs(len(mixed) / 16000 - final["duration_s"]) < 0.1
    svc.bus.unsubscribe(sub)


def test_only_one_recording_and_stop_errors(services):
    svc = services
    try:
        svc.recorder.stop()
        raise AssertionError("stop without recording must fail")
    except LookupError:
        pass
    session = svc.recorder.start("", "note", mic=True, system=False, language="auto")
    assert session["title"].startswith("Nota de voz") and session["sources"]["system"] is False
    try:
        svc.recorder.start("otra", "note", True, False, "auto")
        raise AssertionError("second recording must be refused")
    except ValueError:
        pass
    try:
        svc.recorder.stop("wrong-id")
        raise AssertionError("wrong id must be refused")
    except LookupError:
        pass
    wait_for(lambda: svc.recorder.current and svc.recorder.current.elapsed >= 15.9)
    svc.recorder.stop(session["id"])
    assert svc.worker.wait_idle(30)
    final = svc.sessions.get(session["id"])
    assert final["status"] == "done" and final["audio_path"].endswith("mic.wav")
    assert {s["speaker"] for s in svc.sessions.segments(session["id"])} == {"S1"}


def test_crash_recovery_finalises_orphans(tmp_path, tracks):
    from conftest import make_config

    from scribe.services import Services

    config = make_config(tmp_path, fake_fixture=f"{tracks[0]},{tracks[1]}")
    first = Services(config)
    first.start()
    session = first.recorder.start("Se cae", "meeting", True, True, "es")
    wait_for(lambda: first.recorder.current and first.recorder.current.elapsed >= 15.9)
    # simulate a crash: close the WAVs without going through stop()
    rec = first.recorder.current
    rec.stop_event.set()
    rec.stream.close()
    rec.thread.join(5)
    first.worker.stop()
    first.db.close()
    second = Services(config)
    second.start()
    try:
        assert second.worker.wait_idle(30)
        recovered = second.sessions.get(session["id"])
        assert recovered["status"] == "done" and recovered["duration_s"] > 15
    finally:
        second.stop()
