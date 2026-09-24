import json

from conftest import wait_for


def test_health_status_devices_settings(client):
    health = client.get("/api/health").json()
    assert health == {
        "service": "scribe-hoard",
        "version": health["version"],
        "dataDirConfigured": True,
        "gpu_lease": "disabled",
    }
    status = client.get("/api/status").json()
    assert status["backend"] == "fake" and status["recording"] is None and status["transcriber"]["name"] == "fake"
    assert status["transcriber"]["gpu_lease"] == "disabled"
    assert status["settings"]["model_size"] == "small"
    devices = client.get("/api/devices").json()
    assert devices["mic"][0]["default"] and devices["system"][0]["kind"] == "system"
    updated = client.put("/api/settings", json={"model_size": "tiny", "vad_sensitivity": 3}).json()
    assert updated["model_size"] == "tiny" and updated["vad_sensitivity"] == 3
    assert client.put("/api/settings", json={"model_size": "huge"}).status_code == 400
    assert client.put("/api/settings", json={"vad_sensitivity": 9}).status_code == 400
    assert client.post("/api/models/download").json()["ok"] is True


def test_rejects_non_local_hosts(client):
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 403
    assert client.get("/api/status", headers={"origin": "http://evil.example"}).status_code == 403
    assert client.get("/api/status", headers={"sec-fetch-site": "cross-site"}).status_code == 403


def test_session_crud_export_search(client):
    svc = client.services
    started = client.post("/api/sessions/start", json={"title": "Reunión API", "kind": "meeting", "sources": {"mic": True, "system": True}, "language": "es"})
    assert started.status_code == 201, started.text
    session = started.json()
    assert client.post("/api/sessions/start", json={"title": "otra"}).status_code == 409
    assert client.get("/api/status").json()["recording"]["session_id"] == session["id"]
    assert client.delete(f"/api/sessions/{session['id']}").status_code == 409
    wait_for(lambda: svc.recorder.current and svc.recorder.current.elapsed >= 15.9)
    stopped = client.post(f"/api/sessions/{session['id']}/stop")
    assert stopped.status_code == 200 and stopped.json()["status"] == "processing"
    assert client.post(f"/api/sessions/{session['id']}/stop").status_code == 404
    assert svc.worker.wait_idle(30)

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["status"] == "done" and len(detail["segments"]) >= 2
    listing = client.get("/api/sessions", params={"kind": "meeting"}).json()["sessions"]
    assert listing[0]["id"] == session["id"] and listing[0]["first_line"]
    assert client.get("/api/sessions", params={"kind": "bogus"}).status_code == 400
    assert client.get("/api/sessions", params={"from": "nunca"}).status_code == 400
    assert client.get("/api/sessions", params={"from": "hoy"}).json()["sessions"][0]["id"] == session["id"]

    patched = client.patch(f"/api/sessions/{session['id']}", json={"title": "Renombrada", "tags": ["Demo"], "notes": "Nota", "kind": "interview"}).json()
    assert patched["title"] == "Renombrada" and patched["tags"] == ["demo"] and patched["kind"] == "interview"
    assert client.get("/api/tags").json()["tags"] == [{"tag": "demo", "count": 1}]
    assert client.patch(f"/api/sessions/{session['id']}", json={"kind": "party"}).status_code == 400
    assert client.patch("/api/sessions/nope", json={"title": "x"}).status_code == 404

    for fmt in ("txt", "srt", "md"):
        response = client.get(f"/api/sessions/{session['id']}/export", params={"format": fmt})
        assert response.status_code == 200 and f".{fmt}" in response.headers["content-disposition"]
    assert client.get(f"/api/sessions/{session['id']}/export", params={"format": "pdf"}).status_code == 400
    assert "Renombrada" in client.get(f"/api/sessions/{session['id']}/export", params={"format": "md"}).text

    audio = client.get(f"/api/sessions/{session['id']}/audio")
    assert audio.status_code == 200 and audio.headers["content-type"].startswith("audio/wav")
    partial = client.get(f"/api/sessions/{session['id']}/audio", headers={"range": "bytes=0-99"})
    assert partial.status_code == 206 and len(partial.content) == 100
    peaks = client.get(f"/api/sessions/{session['id']}/peaks", params={"n": 50}).json()
    assert len(peaks["peaks"]) == 50 and peaks["duration_s"] > 15

    search = client.get("/api/search", params={"q": "salario"}).json()
    assert search["total"] >= 1 and search["sessions"][0]["session"]["id"] == session["id"]
    assert "<mark>" in search["sessions"][0]["hits"][0]["snippet"]
    assert client.get("/api/search", params={"q": "salario", "kind": "nope"}).status_code == 400

    assert client.post(f"/api/sessions/{session['id']}/retranscribe").json()["ok"] is True
    assert svc.worker.wait_idle(30) and client.get(f"/api/sessions/{session['id']}").json()["status"] == "done"
    assert client.delete(f"/api/sessions/{session['id']}").json()["ok"] is True
    assert client.get(f"/api/sessions/{session['id']}").status_code == 404


def test_sse_live_generator_yields_segments_then_done(client):
    """The SSE generator itself (the HTTP stream is exercised against the real server in test_e2e)."""
    import asyncio

    from scribe.live import live_events

    svc = client.services
    session = client.post("/api/sessions/start", json={"title": "SSE", "kind": "note", "sources": {"mic": True, "system": False}}).json()
    chunks = []

    async def consume():
        async for chunk in live_events(svc, session["id"], poll_s=0.05):
            chunks.append(chunk)
            if chunk.startswith("event: segment") and svc.recorder.current and svc.recorder.current.elapsed >= 15.9:
                svc.recorder.stop()

    asyncio.run(consume())
    events = [c.split("\n")[0][7:] for c in chunks if c.startswith("event: ")]
    assert events[0] == "status" and "segment" in events and events[-1] == "done"
    done = json.loads(chunks[-1].split("\n")[1][6:])
    assert done["status"] == "done" and done["segments"] >= 1 and done["duration_s"] > 15
    live = [json.loads(c.split("\n")[1][6:]) for c in chunks if c.startswith("event: segment")]
    assert live and all(d["live"] for d in live)  # the UI refetches the definitive segments on `done`
    assert client.get("/api/sessions/none/live").status_code == 404
    # a finished session answers status + done at once
    with client.stream("GET", f"/api/sessions/{session['id']}/live") as response:
        body = "".join(response.iter_text())
    assert body.startswith("event: status") and body.rstrip().endswith('data: {"status": "done"}')
