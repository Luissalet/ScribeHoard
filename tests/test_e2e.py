"""Boot the real app in a subprocess, then talk to it over HTTP and through the MCP stdio bridge."""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from scribe.port import free_port

ROOT = Path(__file__).resolve().parent.parent


def wait_health(url: str, process: subprocess.Popen, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"app exited early with code {process.returncode}")
        try:
            if httpx.get(f"{url}/api/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise AssertionError("app did not become healthy")


@pytest.fixture
def app_process(tmp_path):
    port = free_port()
    data_dir = tmp_path / "data"
    env = {
        **os.environ,
        "SCRIBE_DATA_DIR": str(data_dir),
        "SCRIBE_PORT": str(port),
        "PORT_STRICT": "1",
        "SCRIBE_AUDIO": "fake",
        "SCRIBE_TRANSCRIBER": "fake",
        "SCRIBE_FAKE_SPEED": "0",
        "PYTHONUNBUFFERED": "1",
    }
    process = subprocess.Popen([sys.executable, "-m", "scribe"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        wait_health(url, process)
        yield url, data_dir, env
    finally:
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()


def test_subprocess_http_and_mcp_bridge(app_process):
    url, data_dir, env = app_process
    health = httpx.get(f"{url}/api/health").json()
    assert health["service"] == "scribe-hoard" and health["dataDirConfigured"] is True
    tools = httpx.get(f"{url}/api/agent/tools").json()["tools"]
    assert [t["name"] for t in tools][:2] == ["scribe_status", "scribe_sessions"]

    token = (data_dir / "mcp-token").read_text().strip()
    assert len(token) == 64
    auth = {"Authorization": f"Bearer {token}"}
    assert httpx.post(f"{url}/api/agent/call", json={"name": "scribe_status"}).status_code == 401
    status = httpx.post(f"{url}/api/agent/call", json={"name": "scribe_status"}, headers=auth).json()
    assert status["recording"] is None and status["backend"] == "fake"

    # record with the synthetic fixture through the HTTP API, then read it back through the tools
    started = httpx.post(f"{url}/api/agent/call", json={"name": "scribe_start", "arguments": {"title": "E2E", "kind": "note"}}, headers=auth).json()
    sid = started["session"]["id"]
    deadline = time.time() + 30
    while time.time() < deadline:
        if httpx.get(f"{url}/api/status").json()["recording"]["elapsed_s"] >= 7.9:
            break
        time.sleep(0.2)
    stopped = httpx.post(f"{url}/api/agent/call", json={"name": "scribe_stop", "arguments": {"session_id": sid}}, headers=auth).json()
    assert stopped["stopped"] is True
    deadline = time.time() + 30
    while time.time() < deadline:
        if httpx.get(f"{url}/api/sessions/{sid}").json()["status"] == "done":
            break
        time.sleep(0.2)
    assert httpx.get(f"{url}/api/sessions/{sid}").json()["status"] == "done"

    async def through_mcp():
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command=sys.executable,
            args=[str(ROOT / "mcp_server.py")],
            env={**env, "SCRIBE_URL": url, "SCRIBE_TOKEN_FILE": str(data_dir / "mcp-token")},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert "scribe_transcript" in (init.instructions or "")
                listed = await session.list_tools()
                names = [t.name for t in listed.tools]
                assert names == [t["name"] for t in tools]
                destructive = next(t for t in listed.tools if t.name == "scribe_delete")
                assert destructive.annotations.destructiveHint is True
                payload = json.loads((await session.call_tool("scribe_status", {})).content[0].text)
                assert payload["recording"] is None
                transcript = json.loads((await session.call_tool("scribe_transcript", {"session_id": sid})).content[0].text)
                assert transcript["status"] == "done" and transcript["segments"]
                bad = json.loads((await session.call_tool("scribe_transcript", {"session_id": "nope"})).content[0].text)
                assert "error" in bad

    asyncio.run(through_mcp())
