import importlib

import pytest


@pytest.mark.asyncio
async def test_approval_flow_times_out_and_denies(monkeypatch):
    monkeypatch.setenv("LATCH_APPROVAL_TIMEOUT_SEC", "0.01")
    approval = importlib.import_module("latch.approval")
    approval = importlib.reload(approval)
    monkeypatch.setattr(approval.webbrowser, "open", lambda _url: True)

    approved, reason = await approval.start_approval_flow(
        "Bash",
        {"cmd": "echo test"},
        require_webauthn=False,
    )

    assert approved is False
    assert "timeout" in reason
