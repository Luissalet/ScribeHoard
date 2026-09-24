"""GPU memory leasing (Hoard Link) around the CUDA whisper load.

Never touches a real GPU or a real hub: `faster_whisper.WhisperModel` and
`scribe.transcribe.whisper.lease` are both faked. These tests cover the load
path (granted / timeout / hub-down-falls-back-locally), that the lease is
released after the first transcription and not requested again after that,
and that the state is surfaced in /api/health and /api/status.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from scribe.audio.wav import SAMPLE_RATE
from scribe.hoard_link.lease import LeaseError, LeaseTimeout
from scribe.transcribe import whisper as whisper_mod
from scribe.transcribe.whisper import WhisperTranscriber


def tone(seconds: float = 1.0) -> np.ndarray:
    return (np.sin(np.linspace(0, 20, int(SAMPLE_RATE * seconds))) * 3000).astype(np.int16)


class FakeSegment(SimpleNamespace):
    pass


class FakeWhisperModel:
    """Stands in for faster_whisper.WhisperModel: records how it was built, never loads anything real."""

    instances: list["FakeWhisperModel"] = []
    fail_devices: set[str] = set()

    def __init__(self, size, device, compute_type, download_root):
        if device in FakeWhisperModel.fail_devices:
            raise RuntimeError(f"simulated {device} load failure")
        self.size, self.device, self.compute_type, self.download_root = size, device, compute_type, download_root
        FakeWhisperModel.instances.append(self)

    def transcribe(self, audio, **kwargs):
        seg = FakeSegment(start=0.0, end=1.0, text="hola", avg_logprob=-0.1, no_speech_prob=0.05, compression_ratio=1.1, words=[])
        return [seg], SimpleNamespace()


class FakeLeaseHandle:
    def __init__(self, via: str):
        self.via = via
        self.released = False

    def release(self) -> None:
        self.released = True


class FakeLeaseCall:
    """What `lease(...)` returns before `.acquire()`; records the request and lets the test script the outcome."""

    def __init__(self, kwargs: dict, outcomes: list):
        self.kwargs = kwargs
        self._outcomes = outcomes

    def acquire(self) -> FakeLeaseHandle:
        outcome = self._outcomes.pop(0) if self._outcomes else "granted"
        if outcome == "timeout":
            raise LeaseTimeout("GPU lease still queued after timeout")
        if outcome == "refused":
            raise LeaseError("hub refused the lease")
        return FakeLeaseHandle(via=outcome)  # "hub" or "local"


@pytest.fixture(autouse=True)
def reset_fake_model():
    FakeWhisperModel.instances = []
    FakeWhisperModel.fail_devices = set()
    yield
    FakeWhisperModel.instances = []
    FakeWhisperModel.fail_devices = set()


def install_fake_lease(monkeypatch, outcomes: list) -> list:
    """Patches scribe.transcribe.whisper.lease; returns the list of request kwargs it was called with."""
    calls: list[dict] = []

    def fake_lease(**kwargs):
        calls.append(kwargs)
        return FakeLeaseCall(kwargs, outcomes)

    monkeypatch.setattr(whisper_mod, "lease", fake_lease)
    return calls


def install_fake_model(monkeypatch):
    fake_module = SimpleNamespace(WhisperModel=FakeWhisperModel)
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", fake_module)


def make_transcriber(tmp_path, size="small", device="cuda") -> WhisperTranscriber:
    return WhisperTranscriber(tmp_path / "models", size=size, device=device, compute_type="auto")


# ---------- vram / env helpers ----------

def test_vram_by_size_and_override(monkeypatch):
    assert whisper_mod.whisper_vram_mb("tiny") == 1024
    assert whisper_mod.whisper_vram_mb("base") == 1536
    assert whisper_mod.whisper_vram_mb("small") == 2048
    assert whisper_mod.whisper_vram_mb("medium") == 5120
    assert whisper_mod.whisper_vram_mb("large-v3") == 6144
    assert whisper_mod.whisper_vram_mb("turbo") == 6144
    assert whisper_mod.whisper_vram_mb("distil-large-v3") == 6144
    assert whisper_mod.whisper_vram_mb("something-unknown") == whisper_mod.DEFAULT_VRAM_MB

    monkeypatch.setenv("SCRIBE_WHISPER_VRAM_MB", "3333")
    assert whisper_mod.whisper_vram_mb("tiny") == 3333
    monkeypatch.delenv("SCRIBE_WHISPER_VRAM_MB", raising=False)


def test_gpu_leasing_enabled_toggle(monkeypatch):
    monkeypatch.delenv("SCRIBE_GPU_LEASE", raising=False)
    assert whisper_mod.gpu_leasing_enabled() is True
    monkeypatch.setenv("SCRIBE_GPU_LEASE", "0")
    assert whisper_mod.gpu_leasing_enabled() is False
    monkeypatch.setenv("SCRIBE_GPU_LEASE", "1")
    assert whisper_mod.gpu_leasing_enabled() is True


def test_lease_timeout_env_default_and_override(monkeypatch):
    monkeypatch.delenv("SCRIBE_LEASE_TIMEOUT_S", raising=False)
    assert whisper_mod.lease_timeout_s() == whisper_mod.DEFAULT_LEASE_TIMEOUT_S == 120.0
    monkeypatch.setenv("SCRIBE_LEASE_TIMEOUT_S", "45")
    assert whisper_mod.lease_timeout_s() == 45.0
    monkeypatch.delenv("SCRIBE_LEASE_TIMEOUT_S", raising=False)


# ---------- load path ----------

def test_lease_granted_wraps_load_and_releases_after_first_transcription(tmp_path, monkeypatch):
    install_fake_model(monkeypatch)
    calls = install_fake_lease(monkeypatch, outcomes=["hub"])
    t = make_transcriber(tmp_path)

    t.ensure_loaded()
    assert t.gpu_lease_state == "granted"
    assert t._active_lease is not None and t._lease_pending_release is True
    assert len(calls) == 1
    assert calls[0]["vram_mb"] == 2048  # "small"
    assert calls[0]["owner"] == "scribe" and "whisper" in calls[0]["purpose"]
    assert FakeWhisperModel.instances[-1].device == "cuda"

    held_lease = t._active_lease
    t.transcribe(tone())
    assert held_lease.released is True
    assert t._active_lease is None and t._lease_pending_release is False
    assert t.gpu_lease_state == "granted"  # last known outcome stays visible

    # A second transcription does not ask for a new lease (the model is resident).
    t.transcribe(tone())
    assert len(calls) == 1


def test_lease_hub_down_falls_back_locally_but_still_granted(tmp_path, monkeypatch):
    install_fake_model(monkeypatch)
    install_fake_lease(monkeypatch, outcomes=["local"])  # hub unreachable, local free-VRAM check used
    t = make_transcriber(tmp_path)

    t.ensure_loaded()
    assert t.gpu_lease_state == "granted"
    assert FakeWhisperModel.instances[-1].device == "cuda"


def test_lease_timeout_falls_back_to_cpu(tmp_path, monkeypatch):
    install_fake_model(monkeypatch)
    calls = install_fake_lease(monkeypatch, outcomes=["timeout"])
    t = make_transcriber(tmp_path)

    t.ensure_loaded()
    assert t.gpu_lease_state == "fallback_cpu"
    assert t._active_lease is None
    assert FakeWhisperModel.instances[-1].device == "cpu"
    assert t.loaded_key[1] == "cpu"
    assert len(calls) == 1


def test_lease_refused_falls_back_to_cpu(tmp_path, monkeypatch):
    install_fake_model(monkeypatch)
    install_fake_lease(monkeypatch, outcomes=["refused"])
    t = make_transcriber(tmp_path)

    t.ensure_loaded()
    assert t.gpu_lease_state == "fallback_cpu"
    assert FakeWhisperModel.instances[-1].device == "cpu"


def test_gpu_lease_disabled_env_skips_leasing(tmp_path, monkeypatch):
    install_fake_model(monkeypatch)
    calls = install_fake_lease(monkeypatch, outcomes=["hub"])
    monkeypatch.setenv("SCRIBE_GPU_LEASE", "0")
    t = make_transcriber(tmp_path)

    t.ensure_loaded()
    assert t.gpu_lease_state == "disabled"
    assert calls == []
    assert FakeWhisperModel.instances[-1].device == "cuda"
    monkeypatch.delenv("SCRIBE_GPU_LEASE", raising=False)


def test_cpu_device_never_requests_a_lease(tmp_path, monkeypatch):
    install_fake_model(monkeypatch)
    calls = install_fake_lease(monkeypatch, outcomes=["hub"])
    t = make_transcriber(tmp_path, device="cpu")

    t.ensure_loaded()
    assert t.gpu_lease_state == "disabled"
    assert calls == []


def test_lease_released_when_cuda_load_itself_fails(tmp_path, monkeypatch):
    install_fake_model(monkeypatch)
    calls = install_fake_lease(monkeypatch, outcomes=["hub"])
    FakeWhisperModel.fail_devices = {"cuda"}
    t = make_transcriber(tmp_path)

    t.ensure_loaded()  # falls back to cpu inside ensure_loaded's own except-branch
    assert t.loaded_key[1] == "cpu"
    assert t._active_lease is None  # released, not leaked, once the cuda attempt failed
    assert len(calls) == 1


def test_health_and_status_surface_gpu_lease(client, monkeypatch):
    # The fixture app uses the fake transcriber/backend; health/status still expose the field.
    health = client.get("/api/health").json()
    assert health["gpu_lease"] == "disabled"
    status = client.get("/api/status").json()
    assert status["transcriber"]["gpu_lease"] == "disabled"
