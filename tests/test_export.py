from scribe.export import hms, render

SESSION = {"title": "Reunión de prueba", "started_at": 1_800_000_000.0, "kind": "meeting", "duration_s": 125.5, "notes": "Acordado: nada.", "tags": ["demo", "ficticio"]}
SEGMENTS = [
    {"start_s": 0.0, "end_s": 2.25, "speaker": "yo", "text": "Hola a todos."},
    {"start_s": 2.5, "end_s": 3.0, "speaker": "otros", "text": "Hola."},
    {"start_s": 3661.2, "end_s": 3663.0, "speaker": "yo", "text": "Una hora después."},
]


def test_hms():
    assert hms(0) == "00:00" and hms(65.4) == "01:05" and hms(3661) == "01:01:01"
    assert hms(2.25, millis=True) == "00:00:02,250" and hms(3661.2, millis=True) == "01:01:01,200"


def test_srt_blocks():
    srt = render("srt", SESSION, SEGMENTS)
    blocks = srt.strip().split("\n\n")
    assert len(blocks) == 3
    assert blocks[0] == "1\n00:00:00,000 --> 00:00:02,250\nyo: Hola a todos."
    assert blocks[1] == "2\n00:00:02,500 --> 00:00:03,000\notros: Hola."  # min 0.5 s display
    assert blocks[2].startswith("3\n01:01:01,200 --> 01:01:03,000")


def test_markdown_and_txt():
    md = render("md", SESSION, SEGMENTS)
    assert md.startswith("# Reunión de prueba\n")
    assert "- Etiquetas: demo, ficticio" in md and "## Notas" in md and "Acordado: nada." in md
    assert "**yo**" in md and "**otros**" in md and "- `01:01:01` Una hora después." in md
    txt = render("txt", SESSION, SEGMENTS)
    assert "[00:00] yo: Hola a todos." in txt and "[01:01:01] yo: Una hora después." in txt and txt.endswith("\n")
    assert render("txt", {**SESSION, "notes": ""}, []).count("Notas") == 0
