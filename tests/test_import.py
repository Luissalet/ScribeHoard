import shutil

import numpy as np

from scribe.audio.wav import SAMPLE_RATE, write_wav
from scribe.importer import convert_to_wav, ffmpeg_path


def test_import_wav_creates_transcribed_session(client, tmp_path):
    source = tmp_path / "nota.wav"
    write_wav(source, np.zeros(44100 * 3, dtype=np.int16), 44100)  # 44.1 kHz gets resampled
    with source.open("rb") as handle:
        response = client.post("/api/import", files={"file": ("Nota de voz.wav", handle, "audio/wav")}, data={"title": "Importada", "kind": "note"})
    assert response.status_code == 201, response.text
    session = response.json()
    assert session["origin"] == "import" and session["kind"] == "note" and session["status"] in ("processing", "done")
    assert client.services.worker.wait_idle(30)
    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["status"] == "done" and abs(detail["duration_s"] - 3.0) < 0.05
    assert detail["segments"] and all(s["speaker"] == "S1" for s in detail["segments"])
    assert client.get(f"/api/sessions/{session['id']}/audio").status_code == 200


def test_import_rejects_unknown_extension(client):
    response = client.post("/api/import", files={"file": ("notas.txt", b"hola", "text/plain")})
    assert response.status_code == 400 and "Unsupported" in response.json()["error"]


def test_convert_with_ffmpeg_when_present(tmp_path):
    if not ffmpeg_path():
        return
    source = tmp_path / "in.wav"
    write_wav(source, np.zeros(SAMPLE_RATE, dtype=np.int16))
    ogg = tmp_path / "in.ogg"
    import subprocess

    subprocess.run([ffmpeg_path(), "-y", "-loglevel", "error", "-i", str(source), str(ogg)], check=True)
    assert convert_to_wav(ogg, tmp_path / "out.wav") == "ffmpeg" and (tmp_path / "out.wav").stat().st_size > 1000
    shutil.rmtree(tmp_path / "nothing", ignore_errors=True)
