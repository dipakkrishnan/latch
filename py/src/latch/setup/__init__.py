from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import ui
from .steps import (
    SetupContext,
    cleanup_runtime,
    step_config_dir,
    step_enrollment,
    step_openclaw,
    step_persist_env,
    step_policy,
    step_servers,
    step_summary,
    step_test_flow,
    step_transport,
    step_tunnel,
    step_welcome,
)


@dataclass
class SetupState:
    config_dir: Path = field(default_factory=lambda: Path.home() / ".agent-2fa")
    policy: dict | None = None
    policy_name: str = "Balanced"
    servers: list[dict] = field(default_factory=list)
    transport: str = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000
    mcp_path: str = "/mcp"
    approval_port: int = 0
    use_quick_tunnel: bool = False
    tunnel_url: str | None = None
    rp_id: str = "localhost"
    origin: str = ""
    passkey_enrolled: bool = False
    openclaw_url: str = ""
    openclaw_config_path: Path | None = None
    env_file_path: Path | None = None
    warnings: list[str] = field(default_factory=list)


def run_setup(config_dir=None, interactive: bool = True, assume_yes: bool = False):
    state = SetupState()
    if config_dir:
        state.config_dir = Path(config_dir).expanduser()
    ctx = SetupContext(total_steps=10, interactive=interactive, assume_yes=assume_yes)

    try:
        step_welcome(state, ctx)
        step_config_dir(state, ctx)
        step_policy(state, ctx)
        step_servers(state, ctx)
        step_transport(state, ctx)
        step_tunnel(state, ctx)
        step_enrollment(state, ctx)
        step_openclaw(state, ctx)
        step_persist_env(state, ctx)
        step_test_flow(state, ctx)
    except KeyboardInterrupt:
        ui.warn("Setup interrupted. Showing partial summary.")
    finally:
        step_summary(state)
        cleanup_runtime()
