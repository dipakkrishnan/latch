import argparse
import json
import sys
from pathlib import Path


def _cmd_init(args):
    from .init import init

    config_dir = Path(args.dir) if args.dir else None
    init(config_dir=config_dir, force=args.force)


def _cmd_hook(args):
    from .hook import main

    main()


def _cmd_serve(args):
    from .serve import main

    main()


def _cmd_dashboard(args):
    from .dashboard import main

    main()


def _cmd_enroll(args):
    from .enroll import main

    main()


def _cmd_status(args):
    from .config import CONFIG_DIR

    print(f"Config dir: {CONFIG_DIR}")
    print(f"  exists: {CONFIG_DIR.exists()}")
    if not CONFIG_DIR.exists():
        return

    policy_path = CONFIG_DIR / "policy.yaml"
    if policy_path.exists():
        import yaml

        policy = yaml.safe_load(policy_path.read_text()) or {}
        rules = policy.get("rules", [])
        print(f"  policy: {len(rules)} rule(s), default={policy.get('defaultAction', 'N/A')}")
    else:
        print("  policy: not found")

    creds_path = CONFIG_DIR / "credentials.json"
    if creds_path.exists():
        creds = json.loads(creds_path.read_text())
        print(f"  credentials: {len(creds)} registered")
    else:
        print("  credentials: not found")

    audit_path = CONFIG_DIR / "audit.jsonl"
    if audit_path.exists():
        lines = [l for l in audit_path.read_text().splitlines() if l.strip()]
        print(f"  audit: {len(lines)} entries")
    else:
        print("  audit: not found")

    servers_path = CONFIG_DIR / "servers.yaml"
    if servers_path.exists():
        import yaml

        servers = yaml.safe_load(servers_path.read_text()) or {}
        server_list = servers.get("servers", [])
        print(f"  servers: {len(server_list)} configured")
    else:
        print("  servers: not found")


def main():
    from . import __version__

    parser = argparse.ArgumentParser(prog="latch", description="Latch — universal gating and audit layer for AI agents")
    parser.add_argument("--version", action="version", version=f"latch {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize latch config directory")
    p_init.add_argument("--dir", help="Config directory (default: ~/.agent-2fa)")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing files")
    p_init.set_defaults(func=_cmd_init)

    p_hook = sub.add_parser("hook", help="Run as a tool-use hook (stdin/stdout)")
    p_hook.set_defaults(func=_cmd_hook)

    p_serve = sub.add_parser("serve", help="Run as an MCP proxy server")
    p_serve.set_defaults(func=_cmd_serve)

    p_dashboard = sub.add_parser("dashboard", help="Launch the web dashboard")
    p_dashboard.set_defaults(func=_cmd_dashboard)

    p_enroll = sub.add_parser("enroll", help="Enroll a WebAuthn passkey")
    p_enroll.set_defaults(func=_cmd_enroll)

    p_status = sub.add_parser("status", help="Show config summary")
    p_status.set_defaults(func=_cmd_status)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)
