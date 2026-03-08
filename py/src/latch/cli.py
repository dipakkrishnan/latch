import argparse
import sys


def _cmd_init(args):
    from pathlib import Path
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
    from . import audit, credentials
    from .policy import load_policy
    from .server_registry import load_servers

    print(f"Config dir: {CONFIG_DIR}")
    if not CONFIG_DIR.exists():
        print("  not initialized (run 'latch init')")
        return

    try:
        policy = load_policy()
        rules = policy.get("rules", [])
        print(f"  policy: {len(rules)} rule(s), default={policy.get('defaultAction', 'N/A')}")
    except Exception:
        print("  policy: not found")

    try:
        creds = credentials.load()
        print(f"  credentials: {len(creds)} registered")
    except Exception:
        print("  credentials: not found")

    try:
        s = audit.stats()
        print(f"  audit: {s['total']} entries")
    except Exception:
        print("  audit: not found")

    try:
        servers = load_servers().get("servers", [])
        print(f"  servers: {len(servers)} configured")
    except Exception:
        print("  servers: not found")


def _parse_env_items(items):
    env = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"Invalid --env value: {item!r} (expected KEY=VALUE)")
        k, v = item.split("=", 1)
        if not k:
            raise ValueError(f"Invalid --env value: {item!r} (missing key)")
        env[k] = v
    return env


def _cmd_add_server(args):
    from .server_registry import upsert_server

    env = _parse_env_items(args.env)
    result = upsert_server(
        alias=args.alias,
        command=args.command,
        args=args.args or [],
        env=env or None,
    )
    print(f"Server {result}: alias={args.alias} command={args.command} args={args.args or []}")
    if env:
        print(f"  env keys: {sorted(env.keys())}")


def _cmd_remove_server(args):
    from .server_registry import delete_server

    deleted = delete_server(args.alias)
    if not deleted:
        print(f"Server not found: {args.alias}")
        return
    print(f"Server removed: {args.alias}")


def _cmd_list_servers(args):
    from .server_registry import load_servers

    servers = load_servers().get("servers", [])
    if not servers:
        print("No servers configured.")
        return
    for server in servers:
        args_display = " ".join(server.get("args", []))
        print(f"- {server['alias']}: {server['command']} {args_display}".rstrip())


def _prompt_server_inputs():
    alias = input("Server alias (e.g. fs): ").strip()
    command = input("Server command (e.g. npx): ").strip()
    raw_args = input("Server args (space-separated): ").strip()
    args = raw_args.split() if raw_args else []
    return alias, command, args


def _cmd_onboard(args):
    from . import credentials
    from .init import init
    from .policy import apply_mcp_onboard_policy
    from .server_registry import load_servers, upsert_server
    from .enroll import main as enroll_main

    print("Running latch onboarding...")
    init(force=False)

    servers = load_servers(force=True).get("servers", [])
    if not servers:
        alias = args.server_alias
        command = args.server_command
        server_args = list(args.server_arg or [])
        if args.interactive and (not alias or not command):
            alias, command, prompted_args = _prompt_server_inputs()
            if not server_args:
                server_args = prompted_args
        if not alias or not command:
            print(
                "No downstream servers configured.\n"
                "Provide --server-alias and --server-command (and optionally --server-arg),\n"
                "or run with --interactive.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        env = _parse_env_items(args.server_env)
        outcome = upsert_server(alias=alias, command=command, args=server_args, env=env or None)
        print(f"Server {outcome}: {alias}")
        servers = load_servers(force=True).get("servers", [])
    else:
        print(f"Found {len(servers)} existing server(s); skipping server bootstrap.")

    if not args.keep_policy:
        apply_mcp_onboard_policy()
        print("Applied MCP-safe onboarding policy.")
    else:
        print("Keeping existing policy (--keep-policy).")

    creds = credentials.load()
    if not args.skip_enroll and not creds:
        print("No credentials enrolled; launching passkey enrollment...")
        enroll_main()
        creds = credentials.load()
    elif args.skip_enroll:
        print("Skipped enrollment (--skip-enroll).")
    else:
        print(f"Credentials already enrolled: {len(creds)}")

    print("\nOnboarding complete.")
    print(f"  servers: {len(servers)} configured")
    print(f"  credentials: {len(creds)} registered")
    print("Next steps:")
    print("  1) latch serve")
    print("  2) latch dashboard")


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

    p_add_server = sub.add_parser("add-server", help="Add or update a downstream MCP server")
    p_add_server.add_argument("alias", help="Server alias (used as tool namespace prefix)")
    p_add_server.add_argument("command", help="Command to launch downstream MCP server")
    p_add_server.add_argument("args", nargs="*", help="Arguments for downstream server command")
    p_add_server.add_argument(
        "--env",
        action="append",
        default=[],
        help="Environment variable assignment KEY=VALUE (repeatable)",
    )
    p_add_server.set_defaults(func=_cmd_add_server)

    p_remove_server = sub.add_parser("remove-server", help="Remove a downstream MCP server by alias")
    p_remove_server.add_argument("alias", help="Server alias")
    p_remove_server.set_defaults(func=_cmd_remove_server)

    p_list_servers = sub.add_parser("list-servers", help="List configured downstream MCP servers")
    p_list_servers.set_defaults(func=_cmd_list_servers)

    p_onboard = sub.add_parser("onboard", help="Guided first-run setup for MCP mode")
    p_onboard.add_argument("--interactive", action="store_true", help="Prompt for missing server inputs")
    p_onboard.add_argument("--skip-enroll", action="store_true", help="Skip passkey enrollment step")
    p_onboard.add_argument("--keep-policy", action="store_true", help="Keep existing policy.yaml")
    p_onboard.add_argument("--server-alias", help="Server alias to configure when none exist")
    p_onboard.add_argument("--server-command", help="Server command to configure when none exist")
    p_onboard.add_argument(
        "--server-arg",
        action="append",
        default=[],
        help="Server argument (repeatable), e.g. --server-arg=-y",
    )
    p_onboard.add_argument(
        "--server-env",
        action="append",
        default=[],
        help="Server env assignment KEY=VALUE (repeatable)",
    )
    p_onboard.set_defaults(func=_cmd_onboard)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)
