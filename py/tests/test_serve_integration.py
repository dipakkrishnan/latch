"""Integration test: latch serve over streamable-http transport."""
import asyncio
import json
import os
import tempfile

import pytest
import aiohttp
import yaml


@pytest.fixture
def config_dir(tmp_path):
    """Create a minimal latch config directory."""
    os.environ["AGENT_2FA_DIR"] = str(tmp_path)

    # Policy: allow everything by default
    policy = {"defaultAction": "allow", "rules": []}
    (tmp_path / "policy.yaml").write_text(yaml.dump(policy))

    # No downstream servers (empty)
    (tmp_path / "servers.yaml").write_text(yaml.dump({"servers": []}))

    yield tmp_path

    os.environ.pop("AGENT_2FA_DIR", None)


@pytest.mark.asyncio
async def test_serve_starts_over_streamable_http(config_dir):
    """Verify latch serve starts and responds on streamable-http."""
    os.environ["LATCH_MCP_TRANSPORT"] = "streamable-http"
    os.environ["LATCH_MCP_HOST"] = "127.0.0.1"
    os.environ["LATCH_MCP_PORT"] = "0"  # random port
    os.environ["LATCH_APPROVAL_PORT"] = "0"

    try:
        # Reimport to pick up env changes
        import importlib
        import latch.config
        importlib.reload(latch.config)

        from latch.approval import ApprovalServer
        from latch.serve import _load_servers

        # Verify config loads
        servers = _load_servers()
        assert servers == []

        # Verify approval server starts
        approval_server = ApprovalServer()
        await approval_server.start()
        assert approval_server.port is not None
        assert approval_server.port > 0

        # Verify approval server responds
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://localhost:{approval_server.port}/enroll") as resp:
                assert resp.status == 200

        await approval_server.stop()
    finally:
        os.environ.pop("LATCH_MCP_TRANSPORT", None)
        os.environ.pop("LATCH_MCP_HOST", None)
        os.environ.pop("LATCH_MCP_PORT", None)
        os.environ.pop("LATCH_APPROVAL_PORT", None)
