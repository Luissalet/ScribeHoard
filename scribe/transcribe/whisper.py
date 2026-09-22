"""faster-whisper transcriber: model files under <DATA_DIR>/models, lazy load, cuda when available."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import numpy as np

from ..audio.wav import to_float32
from .base import Segment, Transcriber, Word

log = logging.getLogger("scribe.whisper")
REPO = "Systran/faster-whisper-{size}"
DISTIL_REPO = "Systran/distil-whisper-{size}"


def cuda_available() -> bool:
    try:
        import ctranslate2  # type: ignore

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def resolve_device(device: str) -> str:
    if device == "auto":
        return "cuda" if cuda_available() else "cpu"
    return device


def resolve_compute(compute: str, device: str) -> str:
    if compute != "auto":
        return compute
    return "float16" if device == "cuda" else "int8"


def model_repo(size: str) -> str:
    return (DISTIL_REPO if size.startswith("distil-") else REPO).format(size=size.replace("distil-", ""))


def model_present(models_dir: Path, size: str) -> bool:
    """True when the hub cache under models_dir already holds model.bin for this size."""
    folder = models_dir / ("models--" + model_repo(size).replace("/", "--"))
    return any(folder.glob("snapshots/*/model.bin")) if folder.is_dir() else False


class WhisperTranscriber(Transcriber):
    name = "faster-whisper"

    def __init__(self, models_dir: Path, size: str = "small", device: str = "auto", compute_type: str = "auto"):
        self.models_dir = models_dir
        self.size, self.device_setting, self.compute_setting = size, device, compute_type
        self.model = None
        self.loaded_key: tuple | None = None
        self.state = "idle"  # idle | downloading | loading | ready | error
        self.error = ""
        self.last_ms: int | None = None
        self.lock = threading.RLock()

    # ---------- configuration ----------
    def reconfigure(self, size: str | None = None, device: str | None = None, compute_type: str | None = None, **_: object) -> None:
        with self.lock:
            self.size = size or self.size
            self.device_setting = device or self.device_setting
            self.compute_setting = compute_type or self.compute_setting
            if self.loaded_key != self._key():
                self.model, self.loaded_key, self.state = None, None, "idle"

    def _key(self) -> tuple:
        device = resolve_device(self.device_setting)
        return (self.size, device, resolve_compute(self.compute_setting, device))

    def ensure_loaded(self) -> None:
        with self.lock:
            key = self._key()
            if self.model is not None and self.loaded_key == key:
                return
            from faster_whisper import WhisperModel  # heavy import, kept lazy

            size, device, compute = key
            self.state = "loading" if model_present(self.models_dir, size) else "downloading"
            self.error = ""
            self.models_dir.mkdir(parents=True, exist_ok=True)
            try:
                started = time.time()
                self.model = WhisperModel(size, device=device, compute_type=compute, download_root=str(self.models_dir))
                self.loaded_key, self.state = key, "ready"
                log.info("whisper %s loaded on %s/%s in %.1fs", size, device, compute, time.time() - started)
            except Exception as error:
                if device == "cuda":  # fall back to CPU rather than fail the whole session
                    log.warning("cuda load failed (%s); falling back to cpu", error)
                    try:
                        compute = resolve_compute(self.compute_setting, "cpu")
                        self.model = WhisperModel(size, device="cpu", compute_type=compute, download_root=str(self.models_dir))
                        self.loaded_key, self.state = (size, "cpu", compute), "ready"
                        return
                    except Exception as inner:
                        error = inner
                self.model, self.loaded_key, self.state, self.error = None, None, "error", str(error)
                raise

    # ---------- work ----------
    def transcribe(self, samples: np.ndarray, language: str | None = None) -> list[Segment]:
        self.ensure_loaded()
        audio = to_float32(samples)
        if len(audio) == 0:
            return []
        started = time.time()
        with self.lock:
            raw, _info = self.model.transcribe(
                audio,
                language=None if language in (None, "", "auto") else language,
                beam_size=2,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                word_timestamps=True,
                condition_on_previous_text=False,
            )
            segments = [
                Segment(
                    round(float(s.start), 2),
                    round(float(s.end), 2),
                    s.text.strip(),
                    round(float(np.exp(s.avg_logprob)) if s.avg_logprob is not None else 0.0, 3),
                    [Word(round(float(w.start), 2), round(float(w.end), 2), w.word, round(float(w.probability), 3)) for w in (s.words or [])],
                )
                for s in raw
                if s.text.strip()
            ]
        self.last_ms = int((time.time() - started) * 1000)
        return segments

    def info(self) -> dict:
        size, device, compute = self._key()
        return {
            "name": self.name,
            "model": size,
            "device": device,
            "compute_type": compute,
            "cuda": cuda_available(),
            "loaded": self.model is not None and self.loaded_key == (size, device, compute),
            "download": "ready" if model_present(self.models_dir, size) else ("downloading" if self.state == "downloading" else "missing"),
            "state": self.state,
            "error": self.error,
            "last_ms": self.last_ms,
            "models_dir": str(self.models_dir),
        }
