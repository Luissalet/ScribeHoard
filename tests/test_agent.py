from conftest import wait_for

from scribe.agent_tools import TOOLS, call_tool, tool_catalog


def _auth(client):
    return {"Authorization": f"Bearer {client.services.token}"}


def test_catalog_shape_and_synonyms():
    names = [t["name"] for t in tool_catalog()]
    assert names == ["scribe_status", "scribe_sessions", "scribe_transcript", "scribe_search", "scribe_start", "scribe_stop", "scribe_note", "scribe_tag", "scribe_export", "scribe_delete"]
    for tool in TOOLS:
        assert "Sinónimos:" in tool.description and tool.description.splitlines()[-1].startswith("Sinónimos:")
    by_name = {t.name: t for t in TOOLS}
    assert by_name["scribe_delete"].annotations["destructiveHint"] is True
    assert by_name["scribe_start"].annotations == {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
    assert by_name["scribe_search"].annotations["readOnlyHint"] is True
    schema = next(t for t in tool_catalog() if t["name"] == "scribe_search")["inputSchema"]
    assert "from" in schema["properties"] and "q" in schema["required"]


def test_agent_auth_and_errors(client):
    assert client.post("/api/agent/call", json={"name": "scribe_status"}).status_code == 401
    assert client.post("/api/agent/call", json={"name": "scribe_status"}, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/agent/tools").json()["tools"][0]["name"] == "scribe_status"
    assert client.post("/api/agent/call", json={"name": "nope"}, headers=_auth(client)).status_code == 404
    assert client.post("/api/agent/call", json={"name": "scribe_transcript", "arguments": {}}, headers=_auth(client)).status_code == 400
    assert client.post("/api/agent/call", json={"name": "scribe_transcript", "arguments": {"session_id": "zzz"}}, headers=_auth(client)).status_code == 404
    assert client.post("/api/agent/call", json={"name": "scribe_stop", "arguments": {"session_id": "zzz"}}, headers=_auth(client)).status_code == 404


def test_agent_flow_start_stop_transcript_search_note_tag_export_delete(client):
    svc = client.services
    status = call_tool(svc, "scribe_status", {})
    assert status["recording"] is None and status["devices"]["mic"]
    started = call_tool(svc, "scribe_start", {"title": "Entrevista agente", "kind": "interview", "language": "es"})
    assert started["started"] and "scribe_stop" in started["message"]
    sid = started["session"]["id"]
    assert call_tool(svc, "scribe_status", {})["recording"]["session_id"] == sid
    wait_for(lambda: svc.recorder.current and svc.recorder.current.elapsed >= 15.9)
    stopped = call_tool(svc, "scribe_stop", {"session_id": sid})
    assert stopped["stopped"] and svc.worker.wait_idle(30)

    listing = call_tool(svc, "scribe_sessions", {"kind": "interview", "from": "hoy"})
    assert listing["total"] == 1 and listing["sessions"][0]["id"] == sid and listing["sessions"][0]["first_line"]
    transcript = call_tool(svc, "scribe_transcript", {"session_id": sid, "max_chars": 500})
    assert transcript["status"] == "done" and transcript["segments"] and transcript["next_from_s"] is not None
    rest = call_tool(svc, "scribe_transcript", {"session_id": sid, "from_s": transcript["next_from_s"]})
    assert rest["segments"][0]["start_s"] >= transcript["next_from_s"] - 0.01
    assert {s["speaker"] for s in transcript["segments"] + rest["segments"]} == {"yo", "otros"}
    assert all("t" in s for s in transcript["segments"])

    search = call_tool(svc, "scribe_search", {"q": "salario"})
    assert search["total"] >= 1 and search["sessions"][0]["hits"][0]["t"]
    assert call_tool(svc, "scribe_note", {"session_id": sid, "notes": "Acordado: nada."})["notes"] == "Acordado: nada."
    assert call_tool(svc, "scribe_note", {"session_id": sid, "notes": "Segunda"})["notes"] == "Acordado: nada.\nSegunda"
    assert call_tool(svc, "scribe_tag", {"session_id": sid, "add": ["Cliente", "cliente"]})["tags"] == ["cliente"]
    assert call_tool(svc, "scribe_tag", {"session_id": sid, "add": ["demo"], "remove": ["cliente"]})["tags"] == ["demo"]
    export = call_tool(svc, "scribe_export", {"session_id": sid, "format": "srt"})
    assert export["text"].startswith("1\n00:00:0")
    via_http = client.post("/api/agent/call", json={"name": "scribe_export", "arguments": {"session_id": sid, "format": "md"}}, headers=_auth(client)).json()
    assert via_http["text"].startswith("# Entrevista agente")
    assert call_tool(svc, "scribe_delete", {"session_id": sid})["deleted"] is True
    assert call_tool(svc, "scribe_sessions", {})["total"] == 0
