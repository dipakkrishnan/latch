"""Tests for the persistent ApprovalServer."""
import asyncio
import json

import pytest
import pytest_asyncio
import aiohttp

from latch.approval import ApprovalServer
import latch.approval as approval_mod


@pytest_asyncio.fixture
async def server():
    s = ApprovalServer()
    await s.start()
    yield s
    await s.stop()


@pytest.mark.asyncio
async def test_create_request_returns_id_and_url(server):
    aid, url = server.create_request("Bash", {"command": "ls"})
    assert aid
    assert f"/approval/{aid}" in url
    assert url.startswith("http://localhost:")


@pytest.mark.asyncio
async def test_approve_flow(server):
    aid, url = server.create_request("Bash", {"command": "ls"})

    # Simulate approval via HTTP
    async with aiohttp.ClientSession() as session:
        # Page should load
        async with session.get(url) as resp:
            assert resp.status == 200
            body = await resp.text()
            assert "Bash" in body

        # Approve
        decide_url = f"{url}/decide"
        async with session.post(decide_url, json={"decision": "approve"}) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["ok"]

    approved = await asyncio.wait_for(server.wait_for_decision(aid, timeout=2), timeout=3)
    assert approved is True


@pytest.mark.asyncio
async def test_deny_flow(server):
    aid, url = server.create_request("Bash", {"command": "rm -rf /"})

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{url}/decide", json={"decision": "deny"}) as resp:
            assert resp.status == 200

    approved = await asyncio.wait_for(server.wait_for_decision(aid, timeout=2), timeout=3)
    assert approved is False


@pytest.mark.asyncio
async def test_expired_session(server):
    aid, url = server.create_request("Bash", {"command": "ls"})
    # Manually expire
    server._sessions[aid]["created_at"] = 0

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            assert resp.status == 410


@pytest.mark.asyncio
async def test_unknown_session_404(server):
    base = f"http://localhost:{server.port}"
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{base}/approval/nonexistent") as resp:
            assert resp.status == 404


@pytest.mark.asyncio
async def test_wait_for_decision_timeout(server):
    aid, _ = server.create_request("Bash", {"command": "ls"})
    approved = await server.wait_for_decision(aid, timeout=0.1)
    assert approved is False
    # Session should be cleaned up
    assert aid not in server._sessions


@pytest.mark.asyncio
async def test_session_single_use(server):
    aid, url = server.create_request("Bash", {"command": "ls"})

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{url}/decide", json={"decision": "approve"}) as resp:
            assert resp.status == 200

    await server.wait_for_decision(aid, timeout=1)

    # Session should be gone
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{url}/decide", json={"decision": "approve"}) as resp:
            assert resp.status == 404


@pytest.mark.asyncio
async def test_max_sessions_evicts_oldest(server):
    from latch.approval import MAX_SESSIONS

    aids = []
    for i in range(MAX_SESSIONS):
        aid, _ = server.create_request("Tool", {"i": i})
        aids.append(aid)

    assert len(server._sessions) == MAX_SESSIONS

    # Adding one more should evict the oldest
    new_aid, _ = server.create_request("Tool", {"i": "overflow"})
    assert len(server._sessions) == MAX_SESSIONS
    assert aids[0] not in server._sessions
    assert new_aid in server._sessions


@pytest.mark.asyncio
async def test_enrollment_page_loads(server):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://localhost:{server.port}/enroll") as resp:
            assert resp.status == 200
            body = await resp.text()
            assert "Enroll Passkey" in body


@pytest.mark.asyncio
async def test_native_gate_pending_then_deny(server, monkeypatch):
    monkeypatch.setattr(approval_mod, "LATCH_TOKEN", "test-token")
    monkeypatch.setattr(approval_mod, "load_policy", lambda: {"defaultAction": "ask", "rules": []})
    monkeypatch.setattr(approval_mod, "evaluate", lambda tool, policy: ("ask", "test"))

    headers = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}
    base = f"http://localhost:{server.port}"
    payload = {
        "tool": "openclaw.exec",
        "args": {"command": "ls"},
        "sessionKey": "s1",
        "channel": "whatsapp",
        "to": "+14125551234",
        "agentId": "main",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{base}/v1/gate/native", headers=headers, json=payload) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["state"] == "pending"
            approval_id = data["approvalId"]
            assert data["approvalUrl"].endswith(f"/approval/{approval_id}")

        async with session.get(f"{base}/v1/gate/native/{approval_id}", headers=headers) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["state"] == "pending"

        async with session.post(f"{base}/approval/{approval_id}/decide", json={"decision": "deny"}) as resp:
            assert resp.status == 200

        async with session.get(f"{base}/v1/gate/native/{approval_id}", headers=headers) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["state"] == "deny"


@pytest.mark.asyncio
async def test_native_gate_requires_auth_when_token_set(server, monkeypatch):
    monkeypatch.setattr(approval_mod, "LATCH_TOKEN", "expected-token")
    monkeypatch.setattr(approval_mod, "load_policy", lambda: {"defaultAction": "allow", "rules": []})
    monkeypatch.setattr(approval_mod, "evaluate", lambda tool, policy: ("allow", "test"))

    base = f"http://localhost:{server.port}"
    payload = {"tool": "openclaw.exec", "args": {"command": "ls"}}

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{base}/v1/gate/native", json=payload) as resp:
            assert resp.status == 401

        async with session.post(
            f"{base}/v1/gate/native",
            headers={"Authorization": "Bearer expected-token", "Content-Type": "application/json"},
            json=payload,
        ) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["state"] == "allow"
