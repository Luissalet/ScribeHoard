"""Silence gate, decoder-signal filters and the hallucination deny-list (live and final share them)."""

import numpy as np
from conftest import wait_for

from scribe.audio.fake import synth_speechlike
from scribe.audio.wav import SAMPLE_RATE, write_wav
from scribe.store import NO_SPEECH_NOTE
from scribe.transcribe.base import Segment, Transcriber
from scribe.transcribe.fake import FakeTranscriber
from scribe.transcribe.filter import FilterStats, filter_segments, guarded_transcribe, is_hallucination, speech_stats


def silence(seconds=12.0):
    return np.zeros(int(SAMPLE_RATE * seconds), dtype=np.int16)


def hiss(seconds=12.0, amplitude=0.003, seed=1):
    rng = np.random.default_rng(seed)
    return (rng.normal(0, amplitude, int(SAMPLE_RATE * seconds)) * 32767).astype(np.int16)


class Hallucinating(Transcriber):
    """Returns the classic hallucination plus flagged segments; counts calls."""

    name = "hallucinating"

    def __init__(self):
        self.calls = 0

    def transcribe(self, samples, language=None):
        self.calls += 1
        duration = len(samples) / SAMPLE_RATE
        return [
            Segment(0.0, min(3.0, duration), "Este es el canal de subtítulos en español de la comunidad.", 0.4, no_speech_prob=0.2, avg_logprob=-0.5, compression_ratio=1.1),
            Segment(0.0, min(3.0, duration), "Hola, esto sí es una frase real.", 0.9, no_speech_prob=0.1, avg_logprob=-0.4, compression_ratio=1.3),
            Segment(3.0, min(5.0, duration), "Texto inventado con silencio.", 0.5, no_speech_prob=0.9, avg_logprob=-0.4, compression_ratio=1.3),
            Segment(5.0, min(7.0, duration), "Texto de muy baja probabilidad.", 0.2, no_speech_prob=0.1, avg_logprob=-1.7, compression_ratio=1.3),
            Segment(7.0, min(9.0, duration), "la la la la la la la la la la la la.", 0.2, no_speech_prob=0.1, avg_logprob=-0.4, compression_ratio=3.9),
        ]


def test_speech_stats_gate():
    assert not speech_stats(silence()).has_speech
    assert not speech_stats(hiss()).has_speech  # mic noise floor
    assert speech_stats(synth_speechlike(8.0)).has_speech
    short = synth_speechlike(1.0, pattern=[(0.4, 0.5)])  # 100 ms blip is not speech
    assert not speech_stats(short).has_speech


def test_deny_list_is_case_and_accent_insensitive():
    for text in ("Subtítulos realizados por la comunidad de Amara.org", "SUBTITULOS REALIZADOS POR LA COMUNIDAD DE AMARA.ORG", "Gracias por ver el vídeo.", "¡Suscríbete!", "Thank you for watching", "Thanks for watching!", "Este es el canal de subtítulos en español de la televisión pública."):
        assert is_hallucination(text), text
    for text in ("Hola, buenos días.", "Gracias por venir, empezamos con el presupuesto.", "Hoy vamos a hablar del calendario de entregas."):
        assert not is_hallucination(text), text


def test_filter_segments_by_decoder_signals_and_denylist():
    stats = FilterStats()
    kept = filter_segments(Hallucinating().transcribe(silence(9)), stats)
    assert [s.text for s in kept] == ["Hola, esto sí es una frase real."]
    assert (stats.kept, stats.dropped_denylist, stats.dropped_no_speech, stats.dropped_logprob, stats.dropped_compression) == (1, 1, 1, 1, 1)
    assert stats.dropped == 4 and len(stats.dropped_texts) == 4
    # segments without decoder signals (fake backend, None) only go through the deny-list
    assert len(filter_segments([Segment(0, 1, "Hola"), Segment(1, 2, "Thanks for watching")])) == 1


def test_guarded_transcribe_skips_silence_without_calling_the_model():
    model = Hallucinating()
    stats = FilterStats()
    assert guarded_transcribe(model, silence(), "es", 2, stats) == []
    assert guarded_transcribe(model, hiss(), "es", 2, stats) == []
    assert model.calls == 0 and stats.skipped_silent == 2 and stats.chunks == 2
    kept = guarded_transcribe(model, synth_speechlike(9.0), "es", 2, stats)
    assert model.calls == 1 and [s.text for s in kept] == ["Hola, esto sí es una frase real."]
    assert stats.skipped_silent == 2 and stats.dropped == 4 and stats.kept == 1


def test_silent_recording_ends_done_with_no_speech_note(tmp_path):
    from conftest import make_config

    from scribe.services import Services

    fixture = tmp_path / "silence.wav"
    write_wav(fixture, hiss(12.0))
    svc = Services(make_config(tmp_path, fake_fixture=str(fixture)))
    svc.transcriber = svc.pipeline.transcriber = svc.recorder.transcriber = Hallucinating()
    svc.start()
    try:
        session = svc.recorder.start("Silencio", "note", mic=True, system=False, language="es")
        wait_for(lambda: svc.recorder.current and svc.recorder.current.elapsed >= 11.9)
        svc.recorder.stop()
        assert svc.worker.wait_idle(30)
        final = svc.sessions.get(session["id"])
        assert final["status"] == "done" and final["error"] == ""
        assert svc.sessions.segments(session["id"]) == []
        assert final["stats"]["no_speech"] is True and final["stats"]["final"]["skipped_silent"] == 1
        assert svc.transcriber.calls == 0  # the model never saw the silent track
        assert svc.sessions.first_line(session["id"]) == NO_SPEECH_NOTE
        from scribe.agent_tools import call_tool

        listed = call_tool(svc, "scribe_sessions", {})["sessions"][0]
        assert listed["first_line"] == NO_SPEECH_NOTE and listed["no_speech"] is True
        assert "No speech was detected" in call_tool(svc, "scribe_transcript", {"session_id": session["id"]})["note"]
    finally:
        svc.stop()


def test_live_and_final_drop_hallucinations_on_real_speech(tmp_path, tracks):
    from conftest import make_config

    from scribe.services import Services

    svc = Services(make_config(tmp_path, fake_fixture=f"{tracks[0]},{tracks[1]}"))
    svc.transcriber = svc.pipeline.transcriber = svc.recorder.transcriber = Hallucinating()
    svc.start()
    try:
        session = svc.recorder.start("Con voz", "meeting", mic=True, system=True, language="es")
        live = wait_for(lambda: svc.sessions.segments(session["id"]) or None)
        assert all(s["text"] == "Hola, esto sí es una frase real." for s in live)
        wait_for(lambda: svc.recorder.current and svc.recorder.current.elapsed >= 15.9)
        assert svc.recorder.status()["dropped"] >= 4
        svc.recorder.stop()
        assert svc.worker.wait_idle(30)
        final = svc.sessions.get(session["id"])
        texts = {s["text"] for s in svc.sessions.segments(session["id"])}
        assert texts == {"Hola, esto sí es una frase real."} and final["stats"]["no_speech"] is False
        assert final["stats"]["live"]["dropped"] >= 4 and final["stats"]["final"]["dropped"] == 8
    finally:
        svc.stop()


def test_fake_transcriber_passes_the_filter():
    kept = guarded_transcribe(FakeTranscriber(), synth_speechlike(8.0), "es")
    assert len(kept) == 4
