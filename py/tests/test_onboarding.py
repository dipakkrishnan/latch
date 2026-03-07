import argparse
import asyncio
import importlib
from tempfile import TemporaryDirectory

import pytest


def _reload_core_modules():
    importlib.reload(importlib.import_module("latch.config"))
    importlib.reload(importlib.import_module("latch.init"))
    importlib.reload(importlib.import_module("latch.policy"))
    importlib.reload(importlib.import_module("latch.credentials"))
    importlib.reload(importlib.import_module("latch.server_registry"))
    importlib.reload(importlib.import_module("latch.serve"))
    return importlib.reload(importlib.import_module("latch.cli"))


def test_onboard_bootstraps_server_and_policy(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        monkeypatch.setenv("AGENT_2FA_DIR", temp_dir)
        cli = _reload_core_modules()
        policy = importlib.import_module("latch.policy")
        registry = importlib.import_module("latch.server_registry")

        args = argparse.Namespace(
            interactive=False,
            skip_enroll=True,
            keep_policy=False,
            server_alias="fs",
            server_command="npx",
            server_arg=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            server_env=["FOO=bar"],
        )
        cli._cmd_onboard(args)

        servers = registry.load_servers(force=True)["servers"]
        assert len(servers) == 1
        assert servers[0]["alias"] == "fs"
        assert servers[0]["command"] == "npx"
        assert servers[0]["env"] == {"FOO": "bar"}

        loaded_policy = policy.load_policy(force=True)
        assert policy.policy_uses_ask(loaded_policy) is False
        assert loaded_policy["rules"][0]["action"] == "webauthn"


def test_onboard_requires_server_info_when_none_configured(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        monkeypatch.setenv("AGENT_2FA_DIR", temp_dir)
        cli = _reload_core_modules()

        args = argparse.Namespace(
            interactive=False,
            skip_enroll=True,
            keep_policy=False,
            server_alias=None,
            server_command=None,
            server_arg=[],
            server_env=[],
        )
        with pytest.raises(SystemExit) as exc:
            cli._cmd_onboard(args)
        assert exc.value.code == 2


def test_serve_exits_when_no_servers(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        monkeypatch.setenv("AGENT_2FA_DIR", temp_dir)
        _reload_core_modules()
        serve = importlib.import_module("latch.serve")

        with pytest.raises(SystemExit) as exc:
            asyncio.run(serve._run())
        assert exc.value.code == 1
