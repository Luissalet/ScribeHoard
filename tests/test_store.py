import time

from scribe.merge import Labelled
from scribe.store import fts_query, normalize_tags


def _seed(svc):
    a = svc.sessions.create("Entrevista técnica ficticia", "interview", True, True, "es", status="done")
    b = svc.sessions.create("Reunión semanal", "meeting", True, False, "es", status="done", started_at=time.time() - 3 * 86400)
    svc.sessions.add_segments(a["id"], [Labelled(0, 2, "yo", "Hablemos del salario y del horario."), Labelled(2, 5, "otros", "El salario sería de cien monedas.")], live=False)
    svc.sessions.add_segments(b["id"], [Labelled(0, 3, "S1", "Repasamos el presupuesto del trimestre."), Labelled(3, 6, "S1", "Y también los horarios de verano.")], live=False)
    return a, b


def test_fts_query_builder():
    assert fts_query("salario") == '"salario"*'
    assert fts_query('reunión "rara" ok') == '"reunión" "rara" "ok"'
    assert fts_query("  ") == "" and fts_query("--") == ""


def test_search_groups_by_session_with_snippets_and_offsets(services):
    a, b = _seed(services)
    result = services.sessions.search("salario")
    assert result["total"] == 2 and len(result["sessions"]) == 1
    entry = result["sessions"][0]
    assert entry["session"]["id"] == a["id"] and [h["start_s"] for h in entry["hits"]] == [0, 2]
    assert "<mark>salario</mark>" in entry["hits"][0]["snippet"]
    assert entry["hits"][1]["speaker"] == "otros"
    # prefix on the last word, diacritics-insensitive
    assert services.sessions.search("horar")["total"] == 2
    assert services.sessions.search("Presupuesto")["sessions"][0]["session"]["id"] == b["id"]
    # filters
    assert services.sessions.search("horar", kind="meeting")["sessions"][0]["session"]["id"] == b["id"]
    assert services.sessions.search("horar", start=time.time() - 3600)["total"] == 1
    assert services.sessions.search("nada")["total"] == 0


def test_title_is_indexed_and_follows_renames(services):
    a, _ = _seed(services)
    assert services.sessions.search("entrevista")["sessions"][0]["session"]["id"] == a["id"]
    services.sessions.update(a["id"], title="Charla con proveedor")
    assert services.sessions.search("entrevista")["total"] == 0
    assert services.sessions.search("proveedor")["total"] == 2
    assert [s["id"] for s in services.sessions.list(q="proveedor")] == [a["id"]]


def test_list_filters_tags_and_delete(services):
    a, b = _seed(services)
    services.sessions.update(a["id"], tags=["Cliente", "cliente", " demo "])
    assert services.sessions.get(a["id"])["tags"] == ["cliente", "demo"]
    assert normalize_tags(["A", "a", ""]) == ["a"]
    assert [s["id"] for s in services.sessions.list(tag="demo")] == [a["id"]]
    assert [s["id"] for s in services.sessions.list(kind="meeting")] == [b["id"]]
    assert [s["id"] for s in services.sessions.list(start=time.time() - 86400)] == [a["id"]]
    assert services.sessions.tags() == [{"tag": "cliente", "count": 1}, {"tag": "demo", "count": 1}]
    assert services.sessions.first_line(b["id"]).startswith("Repasamos")
    folder = services.sessions.session_dir(a["id"])
    assert folder.is_dir()
    assert services.sessions.delete(a["id"]) is True and not folder.exists()
    assert services.sessions.search("salario")["total"] == 0 and services.sessions.delete(a["id"]) is False


def test_replace_segments_drops_live_ones(services):
    a, _ = _seed(services)
    services.sessions.add_segments(a["id"], [Labelled(5, 6, "yo", "provisional")], live=True)
    assert [s["live"] for s in services.sessions.segments(a["id"])] == [False, False, True]
    services.sessions.replace_segments(a["id"], [Labelled(0, 6, "yo", "definitivo")])
    rows = services.sessions.segments(a["id"])
    assert [(r["text"], r["live"]) for r in rows] == [("definitivo", False)]
    assert services.sessions.search("provisional")["total"] == 0 and services.sessions.search("definitivo")["total"] == 1
    assert services.sessions.segments(a["id"], from_s=7) == []
