import numpy as np

from scribe.audio.fake import synth_speechlike
from scribe.audio.wav import SAMPLE_RATE
from scribe.vad import HAVE_WEBRTCVAD, Chunker, split_track


def _near(value, expected, tol=0.3):
    return abs(value - expected) <= tol


def test_energy_chunker_finds_bursts():
    pattern = [(0.5, 1.6), (3.0, 4.4), (6.0, 6.9)]
    audio = synth_speechlike(8.0, pattern=pattern)
    chunks = split_track(audio, use_webrtc=False)
    assert len(chunks) == 3
    for chunk, (start, end) in zip(chunks, pattern):
        assert _near(chunk.start_s, start) and _near(chunk.end_s, end, 0.9)
        assert len(chunk.samples) == int(round((chunk.end_s - chunk.start_s) * SAMPLE_RATE))


def test_webrtc_chunker_when_available():
    if not HAVE_WEBRTCVAD:
        return
    audio = synth_speechlike(8.0, pattern=[(0.5, 1.6), (3.0, 4.4)])
    chunks = split_track(audio, use_webrtc=True)
    assert len(chunks) == 2 and _near(chunks[0].start_s, 0.5) and _near(chunks[1].start_s, 3.0)


def test_streaming_feed_matches_whole_track():
    audio = synth_speechlike(8.0, pattern=[(0.5, 1.6), (3.0, 4.4)])
    chunker = Chunker(use_webrtc=False)
    streamed = []
    block = 480  # 30 ms blocks with an odd remainder to exercise the pending buffer
    for offset in range(0, len(audio), block + 7):
        streamed += chunker.feed(audio[offset : offset + block + 7])
    streamed += chunker.flush()
    whole = split_track(audio, use_webrtc=False)
    assert [(c.start_s, c.end_s) for c in streamed] == [(c.start_s, c.end_s) for c in whole]


def test_max_chunk_splits_long_speech_and_silence_yields_nothing():
    long_speech = synth_speechlike(12.0, pattern=[(0.2, 11.8)])
    chunks = split_track(long_speech, use_webrtc=False, max_chunk_s=4.0)
    assert len(chunks) >= 3 and all(c.duration <= 4.1 for c in chunks)
    assert split_track(np.zeros(SAMPLE_RATE * 3, dtype=np.int16), use_webrtc=False) == []
