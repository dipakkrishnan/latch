import importlib
from tempfile import TemporaryDirectory

import pytest
from aiohttp.test_utils import TestClient, TestServer


@pytest.mark.asyncio
async def test_dashboard_enroll_verify_requires_challenge_id(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        monkeypatch.setenv("AGENT_2FA_DIR", temp_dir)
        importlib.reload(importlib.import_module("latch.config"))
        importlib.reload(importlib.import_module("latch.credentials"))
        dashboard = importlib.reload(importlib.import_module("latch.dashboard"))

        app = await dashboard.create_app(port=2222)
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                resp = await client.post("/api/enroll/verify", json={})
                assert resp.status == 400
                body = await resp.json()
                assert body["error"] == "Missing challengeId"


@pytest.mark.asyncio
async def test_dashboard_enroll_verify_rejects_non_platform_authenticator(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        monkeypatch.setenv("AGENT_2FA_DIR", temp_dir)
        importlib.reload(importlib.import_module("latch.config"))
        importlib.reload(importlib.import_module("latch.credentials"))
        dashboard = importlib.reload(importlib.import_module("latch.dashboard"))

        app = await dashboard.create_app(port=2222)
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                options_resp = await client.get("/api/enroll/options")
                options = await options_resp.json()
                cid = options["challengeId"]

                resp = await client.post(
                    "/api/enroll/verify",
                    json={"challengeId": cid, "response": {"authenticatorAttachment": "cross-platform"}},
                )
                assert resp.status == 400
                body = await resp.json()
                assert "Platform authenticator required" in body["error"]
