from scribe.merge import coalesce, label_for, merge_tracks
from scribe.transcribe.base import Segment


def test_two_tracks_get_channel_labels_and_time_order():
    per_track = {
        "mic": [Segment(0.5, 3.0, "Hola, empezamos."), Segment(9.0, 10.0, "De acuerdo.")],
        "system": [Segment(3.5, 8.0, "Perfecto, sigo yo."), Segment(10.5, 12.0, "Hasta luego.")],
    }
    merged = merge_tracks(per_track)
    assert [(m.speaker, m.start_s) for m in merged] == [("yo", 0.5), ("otros", 3.5), ("yo", 9.0), ("otros", 10.5)]


def test_single_track_is_s1_and_offsets_apply():
    merged = merge_tracks({"audio": [Segment(1.0, 2.0, "solo")]}, offsets={"audio": 0.25})
    assert merged[0].speaker == "S1" and merged[0].start_s == 1.25
    assert label_for("mic", 1) == "S1" and label_for("mic", 2) == "yo" and label_for("system", 2) == "otros"


def test_overlap_keeps_both_and_blank_text_is_dropped():
    merged = merge_tracks({"mic": [Segment(1.0, 4.0, "yo hablo"), Segment(4.0, 5.0, "   ")], "system": [Segment(2.0, 3.0, "interrumpo")]})
    assert [(m.speaker, m.text) for m in merged] == [("yo", "yo hablo"), ("otros", "interrumpo")]


def test_coalesce_joins_same_speaker_short_gaps_only():
    merged = merge_tracks({"mic": [Segment(0, 1, "uno"), Segment(1.2, 2, "dos"), Segment(5, 6, "tres")], "system": [Segment(2.1, 2.5, "eh")]})
    joined = coalesce(merged, gap_s=0.5)
    assert [(m.speaker, m.text) for m in joined] == [("yo", "uno dos"), ("otros", "eh"), ("yo", "tres")]
    assert joined[0].start_s == 0 and joined[0].end_s == 2
