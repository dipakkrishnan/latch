from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class McporterWriteResult:
    path: Path
    created: bool
    backup_path: Path | None = None


def write_mcporter_config(config_file: Path, latch_url: str) -> McporterWriteResult:
    config_file.parent.mkdir(parents=True, exist_ok=True)
    created = not config_file.exists()
    backup_path: Path | None = None

    data: dict
    if config_file.exists():
        try:
            data = json.loads(config_file.read_text())
        except json.JSONDecodeError:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            backup_path = config_file.with_suffix(config_file.suffix + f".bak.{ts}")
            config_file.replace(backup_path)
            data = {}
    else:
        data = {}

    mcp_servers = data.setdefault("mcpServers", {})
    mcp_servers["latch"] = {"baseUrl": latch_url, "allowHttp": True}
    config_file.write_text(json.dumps(data, indent=2) + "\n")
    return McporterWriteResult(path=config_file, created=created, backup_path=backup_path)


def apply_mcporter_in_container(container: str, content: str) -> tuple[bool, str]:
    cmd = [
        "docker",
        "exec",
        "-i",
        container,
        "sh",
        "-lc",
        "mkdir -p ~/.mcporter && cat > ~/.mcporter/mcporter.json",
    ]
    proc = subprocess.run(cmd, input=content, text=True, capture_output=True)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "unknown docker exec error").strip()
    return True, ""
