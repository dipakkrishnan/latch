import importlib
from tempfile import TemporaryDirectory


def test_server_registry_upsert_update_delete(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        monkeypatch.setenv("AGENT_2FA_DIR", temp_dir)
        importlib.reload(importlib.import_module("latch.config"))
        registry = importlib.reload(importlib.import_module("latch.server_registry"))

        initial = registry.load_servers(force=True)
        assert initial == {"servers": []}

        result = registry.upsert_server(
            alias="fs",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            env={"FOO": "bar"},
        )
        assert result == "added"
        loaded = registry.load_servers(force=True)["servers"]
        assert len(loaded) == 1
        assert loaded[0]["alias"] == "fs"
        assert loaded[0]["env"] == {"FOO": "bar"}

        result = registry.upsert_server(alias="fs", command="node", args=["server.js"])
        assert result == "updated"
        loaded = registry.load_servers(force=True)["servers"]
        assert len(loaded) == 1
        assert loaded[0]["command"] == "node"
        assert loaded[0]["args"] == ["server.js"]

        assert registry.delete_server("fs") is True
        assert registry.load_servers(force=True) == {"servers": []}
        assert registry.delete_server("fs") is False
