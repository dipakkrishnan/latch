import json
import sys
from pathlib import Path

import pytest

from latch.setup.openclaw import write_mcporter_config
from latch.setup.persist import render_env_exports, write_env_file


def test_render_env_exports_quotes_values():
    text = render_env_exports(
        {
            "AGENT_2FA_DIR": "/tmp/a b",
            "LATCH_ORIGIN": "https://example.trycloudflare.com",
        }
    )
    assert "export AGENT_2FA_DIR='/tmp/a b'" in text
    assert "export LATCH_ORIGIN='https://example.trycloudflare.com'" in text


def test_write_env_file(tmp_path: Path):
    path = write_env_file(tmp_path, {"A": "1", "B": "2"})
    assert path.exists()
    body = path.read_text()
    assert "export A='1'" in body
    assert "export B='2'" in body


def test_write_mcporter_config_merges_existing(tmp_path: Path):
    cfg = tmp_path / "mcporter.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "other": {"baseUrl": "http://other:9000/mcp", "allowHttp": True},
                }
            }
        )
    )
    result = write_mcporter_config(cfg, "http://host.docker.internal:8100/mcp")
    assert result.created is False
    data = json.loads(cfg.read_text())
    assert "other" in data["mcpServers"]
    assert data["mcpServers"]["latch"]["baseUrl"] == "http://host.docker.internal:8100/mcp"


def test_write_mcporter_config_invalid_json_backup(tmp_path: Path):
    cfg = tmp_path / "mcporter.json"
    cfg.write_text("{invalid json")
    result = write_mcporter_config(cfg, "http://latch:8100/mcp")
    assert result.backup_path is not None
    assert result.backup_path.exists()
    data = json.loads(cfg.read_text())
    assert data["mcpServers"]["latch"]["baseUrl"] == "http://latch:8100/mcp"


def test_cli_help_includes_setup(monkeypatch, capsys):
    from latch import cli

    monkeypatch.setattr(sys, "argv", ["latch", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    out = capsys.readouterr().out
    assert "setup" in out
