import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scribe.audio.wav import SAMPLE_RATE, read_wav, write_wav  # noqa: E402
from scribe.config import Config  # noqa: E402
from scribe.main import create_app  # noqa: E402
from scribe.services import Services  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


def make_config(tmp_path: Path, **overrides) -> Config:
    base = dict(data_dir=tmp_path / "data", audio_backend="fake", transcriber="fake", fake_speed=0.0, data_dir_configured=True)
    base.update(overrides)
    return Config(**base)


def conversation_tracks(tmp_path: Path) -> tuple[Path, Path]:
    """Two-track fixture: 'yo' speaks at 0.5 s on the mic track, 'otros' answers at 8 s on the system track."""
    yo, _ = read_wav(FIXTURES / "yo.wav")
    otros, _ = read_wav(FIXTURES / "otros.wav")
    total = int(16.0 * SAMPLE_RATE)
    mic = np.zeros(total, dtype=np.int16)
    system = np.zeros(total, dtype=np.int16)
    mic[int(0.5 * SAMPLE_RATE) : int(0.5 * SAMPLE_RATE) + len(yo)] = yo
    system[int(8.0 * SAMPLE_RATE) : int(8.0 * SAMPLE_RATE) + len(otros)] = otros
    mic_path, system_path = tmp_path / "mic-fixture.wav", tmp_path / "system-fixture.wav"
    write_wav(mic_path, mic)
    write_wav(system_path, system)
    return mic_path, system_path


@pytest.fixture
def tracks(tmp_path):
    return conversation_tracks(tmp_path)


@pytest.fixture
def services(tmp_path, tracks):
    svc = Services(make_config(tmp_path, fake_fixture=f"{tracks[0]},{tracks[1]}"))
    svc.start()
    yield svc
    svc.stop()


@pytest.fixture
def client(tmp_path, tracks):
    from fastapi.testclient import TestClient

    app = create_app(make_config(tmp_path, fake_fixture=f"{tracks[0]},{tracks[1]}"))
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        test_client.services = app.state.services
        yield test_client


def wait_for(predicate, timeout: float = 20.0, interval: float = 0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("condition not met in time")
