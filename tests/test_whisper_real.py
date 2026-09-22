"""One real faster-whisper `tiny` run on the Spanish fixture (CPU). Marked `whisper`; skipped when the package is missing."""

import os
from pathlib import Path

import pytest

from scribe.audio.wav import read_wav
from scribe.transcribe import whisper_available

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"

pytestmark = pytest.mark.whisper


@pytest.mark.skipif(not whisper_available(), reason="faster-whisper not installed")
def test_tiny_model_transcribes_spanish_fixture(tmp_path):
    from scribe.transcribe.whisper import WhisperTranscriber

    models_dir = Path(os.environ.get("SCRIBE_MODELS_DIR") or ROOT / "data" / "models")
    if not models_dir.is_dir():
        models_dir = tmp_path / "models"  # first run downloads ~75 MB
    transcriber = WhisperTranscriber(models_dir, "tiny", "cpu", "int8")
    transcriber.ensure_loaded()
    info = transcriber.info()
    assert info["loaded"] and info["download"] == "ready" and info["device"] == "cpu"
    samples, _ = read_wav(FIXTURES / "otros.wav")
    segments = transcriber.transcribe(samples, "es")
    text = " ".join(s.text for s in segments).lower()
    assert segments and segments[0].start >= 0 and segments[-1].end <= len(samples) / 16000 + 0.5
    assert "salario" in text or "reunión" in text or "semana" in text
    assert transcriber.last_ms is not None and all(0 <= s.confidence <= 1 for s in segments)
    assert any(s.words for s in segments)
