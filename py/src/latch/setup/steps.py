from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

from . import ui
from .openclaw import apply_mcporter_in_container, write_mcporter_config
from .persist import write_env_file
from .presets import get_preset, preset_names, rules_rows, to_yaml


@dataclass
class SetupContext:
    total_steps: int = 10
    interactive: bool = True
    assume_yes: bool = False


def step_welcome(state, ctx: SetupContext) -> None:
    ui.header(1, ctx.total_steps, "Welcome")
    ui.section(
        "Latch Setup",
        "A guided setup for policy, transport, passkey enrollment, and OpenClaw integration.",
    )
    py_ok = True
    cloudflared_ok = shutil.which("cloudflared") is not None
    docker_ok = shutil.which("docker") is not None
    if cloudflared_ok:
        ui.success("cloudflared detected")
    else:
        msg = "cloudflared not found (remote enrollment will be limited)"
        state.warnings.append(msg)
        ui.warn(msg)
    if docker_ok:
        ui.success("docker detected")
    else:
        ui.dim("docker not found (OpenClaw auto-apply may be unavailable)")
    if not py_ok:
        state.warnings.append("Unsupported Python version")
    ui.ask_confirm(
        "Continue setup?",
        default=True,
        interactive=ctx.interactive,
        assume_yes=ctx.assume_yes,
    )


def step_config_dir(state, ctx: SetupContext) -> None:
    ui.header(2, ctx.total_steps, "Config Directory")
    chosen = ui.ask_text(
        "Config directory",
        default=str(state.config_dir),
        interactive=ctx.interactive,
    ).strip() or str(state.config_dir)
    state.config_dir = Path(chosen).expanduser()
    state.config_dir.mkdir(parents=True, exist_ok=True)
    os.environ["AGENT_2FA_DIR"] = str(state.config_dir)

    force = False
    if any((state.config_dir / n).exists() for n in ("policy.yaml", "servers.yaml", "credentials.json", "audit.jsonl")):
        if ctx.interactive:
            choice = ui.ask_select(
                "Existing config detected. Choose behavior:",
                ["Keep existing files", "Overwrite default files", "Abort"],
                default="Keep existing files",
                interactive=True,
            )
        else:
            choice = "Keep existing files"
        if choice == "Abort":
            raise KeyboardInterrupt
        force = choice == "Overwrite default files"

    from ..init import init

    init(config_dir=state.config_dir, force=force)
    ui.success(f"Using config dir: {state.config_dir}")


def step_policy(state, ctx: SetupContext) -> None:
    ui.header(3, ctx.total_steps, "Policy Preset")
    default = "Balanced"
    name = ui.ask_select(
        "Choose policy preset",
        choices=preset_names(),
        default=default,
        interactive=ctx.interactive,
    )
    policy = get_preset(name)
    ui.show_rules_table(rules_rows(policy), title=f"{name} Rules")

    customize = ui.ask_confirm(
        "Add one custom rule?",
        default=False,
        interactive=ctx.interactive,
        assume_yes=False,
    )
    if customize:
        pattern = ui.ask_text("Tool regex pattern", default="Bash", interactive=ctx.interactive).strip() or "Bash"
        action = ui.ask_select(
            "Rule action",
            ["allow", "deny", "ask", "browser", "webauthn"],
            default="ask",
            interactive=ctx.interactive,
        )
        policy.setdefault("rules", []).append({"match": {"tool": pattern}, "action": action})

    state.policy = policy
    state.policy_name = name
    yaml_text = to_yaml(policy)
    (state.config_dir / "policy.yaml").write_text(yaml_text)
    ui.show_yaml(yaml_text, title="policy.yaml")
    ui.success("Saved policy.yaml")


def step_servers(state, ctx: SetupContext) -> None:
    ui.header(4, ctx.total_steps, "Downstream MCP Servers")
    servers: list[dict] = []
    add_more = ui.ask_confirm(
        "Add a downstream MCP server?",
        default=False,
        interactive=ctx.interactive,
        assume_yes=False,
    )
    while add_more:
        alias = ui.ask_text("Alias", default=f"server{len(servers)+1}", interactive=ctx.interactive).strip()
        command = ui.ask_text("Command", default="python", interactive=ctx.interactive).strip()
        args_raw = ui.ask_text("Args (shell syntax)", default="", interactive=ctx.interactive).strip()
        env_raw = ui.ask_text("Env (KEY=VAL, comma separated)", default="", interactive=ctx.interactive).strip()

        env: dict[str, str] = {}
        if env_raw:
            for item in env_raw.split(","):
                part = item.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    env[k.strip()] = v.strip()

        servers.append(
            {
                "alias": alias,
                "command": command,
                "args": shlex.split(args_raw) if args_raw else [],
                "env": env,
            }
        )
        add_more = ui.ask_confirm(
            "Add another server?",
            default=False,
            interactive=ctx.interactive,
            assume_yes=False,
        )

    state.servers = servers
    text = yaml.safe_dump({"servers": servers}, sort_keys=False)
    (state.config_dir / "servers.yaml").write_text(text)
    ui.show_yaml(text, title="servers.yaml")
    ui.success(f"Saved servers.yaml ({len(servers)} server(s))")


def step_transport(state, ctx: SetupContext) -> None:
    ui.header(5, ctx.total_steps, "Transport")
    transport_label = ui.ask_select(
        "Choose transport",
        ["stdio", "streamable-http"],
        default="streamable-http",
        interactive=ctx.interactive,
    )
    state.transport = transport_label
    if transport_label == "streamable-http":
        state.mcp_host = ui.ask_text("MCP host", default="0.0.0.0", interactive=ctx.interactive).strip() or "0.0.0.0"
        state.mcp_port = int(ui.ask_text("MCP port", default="8100", interactive=ctx.interactive).strip() or "8100")
        state.mcp_path = ui.ask_text("MCP path", default="/mcp", interactive=ctx.interactive).strip() or "/mcp"
        state.approval_port = int(
            ui.ask_text("Approval port", default="8200", interactive=ctx.interactive).strip() or "8200"
        )
    else:
        state.mcp_host = "127.0.0.1"
        state.mcp_port = 8000
        state.mcp_path = "/mcp"
        state.approval_port = 0
    ui.success(f"Transport configured: {state.transport}")


def step_tunnel(state, ctx: SetupContext) -> None:
    ui.header(6, ctx.total_steps, "Quick Tunnel")
    default = True if ctx.interactive else False
    want_tunnel = ui.ask_confirm(
        "Enable Cloudflare quick tunnel for remote phone enrollment?",
        default=default,
        interactive=ctx.interactive,
        assume_yes=ctx.assume_yes,
    )
    if want_tunnel and shutil.which("cloudflared") is None:
        ui.warn("cloudflared is not installed; tunnel will be skipped.")
        state.warnings.append("Quick tunnel skipped because cloudflared is missing")
        want_tunnel = False
    state.use_quick_tunnel = want_tunnel
    ui.dim("Named tunnel is intentionally out of scope for this release.")


async def _enroll_passkey(state) -> tuple[bool, str]:
    from .. import credentials
    from ..approval import get_approval_server
    from ..tunnel import start_tunnel

    server = await get_approval_server()
    enroll_url: str
    if state.use_quick_tunnel:
        tunnel_url = await start_tunnel(server.port)
        if tunnel_url:
            state.tunnel_url = tunnel_url
            parsed = urlparse(tunnel_url)
            state.rp_id = parsed.hostname or "localhost"
            state.origin = f"https://{state.rp_id}"
            enroll_url = f"{tunnel_url}/enroll"
        else:
            state.warnings.append("Tunnel start failed, falling back to local enrollment")
            state.use_quick_tunnel = False
            enroll_url = f"http://localhost:{server.port}/enroll"
    else:
        enroll_url = f"http://localhost:{server.port}/enroll"

    if state.use_quick_tunnel and state.tunnel_url:
        ui.show_qr(enroll_url)
    else:
        webbrowser.open(enroll_url)
        ui.dim(f"Opened browser: {enroll_url}")

    server._enroll_complete = asyncio.Event()
    try:
        await asyncio.wait_for(server._enroll_complete.wait(), timeout=600)
    except asyncio.TimeoutError:
        return False, "Timed out waiting for passkey enrollment."

    count = len(credentials.load())
    return True, f"Enrollment complete ({count} credential(s))."


def step_enrollment(state, ctx: SetupContext) -> None:
    ui.header(7, ctx.total_steps, "Passkey Enrollment")
    default = False if not ctx.interactive else True
    do_enroll = ui.ask_confirm(
        "Enroll a passkey now?",
        default=default,
        interactive=ctx.interactive,
        assume_yes=ctx.assume_yes,
    )
    if not do_enroll:
        state.warnings.append("Passkey enrollment skipped")
        ui.warn("Skipped passkey enrollment.")
        return

    with ui.spinner("Waiting for passkey enrollment..."):
        ok, message = asyncio.run(_enroll_passkey(state))
    if ok:
        state.passkey_enrolled = True
        ui.success(message)
    else:
        state.warnings.append(message)
        ui.warn(message)


def step_openclaw(state, ctx: SetupContext) -> None:
    ui.header(8, ctx.total_steps, "OpenClaw Integration")
    default = True if ctx.interactive else False
    do_openclaw = ui.ask_confirm(
        "Configure OpenClaw integration now?",
        default=default,
        interactive=ctx.interactive,
        assume_yes=ctx.assume_yes,
    )
    if not do_openclaw:
        return

    choices = [
        "http://latch:8100/mcp",
        "http://host.docker.internal:8100/mcp",
        "Custom URL",
    ]
    selected = ui.ask_select(
        "Latch URL from OpenClaw perspective",
        choices=choices,
        default=choices[1],
        interactive=ctx.interactive,
    )
    if selected == "Custom URL":
        selected = ui.ask_text("Custom Latch MCP URL", default="http://host.docker.internal:8100/mcp", interactive=ctx.interactive)
    state.openclaw_url = selected

    config_file = Path.home() / ".mcporter" / "mcporter.json"
    result = write_mcporter_config(config_file, selected)
    content = config_file.read_text()
    state.openclaw_config_path = config_file
    ui.success(f"{'Created' if result.created else 'Updated'} {result.path}")
    if result.backup_path:
        ui.warn(f"Existing invalid JSON was backed up to {result.backup_path}")

    if shutil.which("docker") is not None and ctx.interactive:
        apply_now = ui.ask_confirm(
            "Auto-apply this mcporter config inside an OpenClaw container?",
            default=False,
            interactive=True,
            assume_yes=False,
        )
        if apply_now:
            container = ui.ask_text("Container name", default="openclaw", interactive=True).strip()
            ok, err = apply_mcporter_in_container(container, content)
            if ok:
                ui.success(f"Applied mcporter config inside container '{container}'")
            else:
                state.warnings.append(f"Docker apply failed: {err}")
                ui.warn(f"Docker apply failed: {err}")

    ui.section(
        "OpenClaw Note",
        'If your workflows need shell tools, ensure OpenClaw permits them (e.g. `tools.alsoAllow: ["exec"]`).',
    )


def step_persist_env(state, ctx: SetupContext) -> None:
    ui.header(9, ctx.total_steps, "Persist Runtime Environment")
    if state.tunnel_url and not state.rp_id:
        parsed = urlparse(state.tunnel_url)
        state.rp_id = parsed.hostname or "localhost"
        state.origin = f"https://{state.rp_id}"
    if not state.rp_id:
        state.rp_id = "localhost"
    values = {
        "AGENT_2FA_DIR": str(state.config_dir),
        "LATCH_APPROVAL_PORT": str(state.approval_port),
        "LATCH_MCP_TRANSPORT": state.transport,
        "LATCH_MCP_HOST": state.mcp_host,
        "LATCH_MCP_PORT": str(state.mcp_port),
        "LATCH_MCP_PATH": state.mcp_path,
        "LATCH_RP_ID": state.rp_id,
        "LATCH_ORIGIN": state.origin,
    }
    state.env_file_path = write_env_file(state.config_dir, values)
    ui.success(f"Wrote {state.env_file_path}")
    ui.dim(f"Use: source {state.env_file_path} && latch serve")


async def _run_test_flow(state) -> tuple[bool, str]:
    from ..approval import get_approval_server

    server = await get_approval_server()
    approval_id, url = server.create_request(
        "latch__setup_test",
        {"note": "setup verification"},
        require_webauthn=state.passkey_enrolled,
    )
    if state.use_quick_tunnel and state.tunnel_url:
        ui.show_qr(url)
    else:
        webbrowser.open(url)
        ui.dim(f"Opened browser: {url}")
    approved = await server.wait_for_decision(approval_id, timeout=300)
    if approved:
        return True, "Approval test succeeded."
    return False, "Approval test timed out or was denied."


def step_test_flow(state, ctx: SetupContext) -> None:
    ui.header(10, ctx.total_steps, "Validation Test")
    default = False if not ctx.interactive else True
    run_test = ui.ask_confirm(
        "Run a live approval test flow now?",
        default=default,
        interactive=ctx.interactive,
        assume_yes=False,
    )
    if not run_test:
        return
    with ui.spinner("Running approval validation flow..."):
        ok, message = asyncio.run(_run_test_flow(state))
    if ok:
        ui.success(message)
    else:
        state.warnings.append(message)
        ui.warn(message)


def step_summary(state) -> None:
    from rich import box
    from rich.table import Table

    ui.console.print()
    table = Table(title="Setup Blueprint", box=box.ROUNDED, border_style=ui.ACCENT)
    table.add_column("Area", style=ui.TEXT)
    table.add_column("Value", style=ui.ACCENT)
    table.add_row("Config Dir", str(state.config_dir))
    table.add_row("Policy", state.policy_name)
    table.add_row("Transport", state.transport)
    if state.transport == "streamable-http":
        table.add_row("MCP Endpoint", f"http://{state.mcp_host}:{state.mcp_port}{state.mcp_path}")
    table.add_row("Tunnel", state.tunnel_url or "disabled")
    table.add_row("Passkey Enrollment", "complete" if state.passkey_enrolled else "skipped/incomplete")
    table.add_row("OpenClaw", state.openclaw_url or "not configured")
    table.add_row("Env File", str(state.env_file_path or "not written"))
    ui.console.print(table)

    if state.warnings:
        body = "\n".join(f"- {w}" for w in state.warnings)
        ui.section("Warnings", body)

    ui.section(
        "Next Commands",
        "\n".join(
            [
                f"source {state.env_file_path}" if state.env_file_path else "source <config>/env.sh",
                "latch serve",
                "latch status",
            ]
        ),
    )


def cleanup_runtime() -> None:
    async def _cleanup():
        from .. import approval
        from ..tunnel import stop_tunnel

        try:
            if getattr(approval, "_server", None) is not None:
                await approval._server.stop()
                approval._server = None
        finally:
            await stop_tunnel()

    asyncio.run(_cleanup())
