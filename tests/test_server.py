import os
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

# Set LATCH_DIR before importing latch modules
os.environ["LATCH_DIR"] = str(Path(__file__).parent / ".latch_test")

from latch.server import _handle_approve


@pytest.fixture
def client(aiohttp_client, loop):
    app = web.Application()
    app.router.add_post("/approve", _handle_approve)
    return loop.run_until_complete(aiohttp_client(app))


@pytest.mark.asyncio
async def test_allow_policy(aiohttp_client):
    app = web.Application()
    app.router.add_post("/approve", _handle_approve)
    client = await aiohttp_client(app)

    resp = await client.post("/approve", json={"command": "ls"})
    data = await resp.json()
    assert data["decision"] == "allow-once"


@pytest.mark.asyncio
async def test_deny_policy(aiohttp_client):
    app = web.Application()
    app.router.add_post("/approve", _handle_approve)
    client = await aiohttp_client(app)

    resp = await client.post("/approve", json={"command": "rm"})
    data = await resp.json()
    assert data["decision"] == "deny"


@pytest.mark.asyncio
async def test_approve_without_enrollment_denies(aiohttp_client):
    app = web.Application()
    app.router.add_post("/approve", _handle_approve)
    client = await aiohttp_client(app)

    # "npm" doesn't match allow or deny rules, so defaults to "approve"
    # With no TOTP enrolled and no webhook, this should deny (fail-safe)
    resp = await client.post("/approve", json={"command": "npm install"})
    data = await resp.json()
    assert data["decision"] == "deny"
    assert "not configured" in data["reason"] or "not enrolled" in data["reason"]
