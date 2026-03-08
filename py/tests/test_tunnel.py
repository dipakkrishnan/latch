"""Tests for tunnel module (no cloudflared dependency)."""
import pytest

from latch.tunnel import get_tunnel_url, stop_tunnel


def test_get_tunnel_url_initially_none():
    assert get_tunnel_url() is None


@pytest.mark.asyncio
async def test_stop_tunnel_when_not_running():
    # Should not raise
    await stop_tunnel()
    assert get_tunnel_url() is None
