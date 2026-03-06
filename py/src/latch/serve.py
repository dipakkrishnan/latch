import asyncio, sys
from fastmcp import FastMCP, Client

from .policy import load_policy, evaluate, policy_uses_ask
from .audit import append
from .approval import start_approval_flow
from .logging_utils import debug_enabled, init_logger
from .server_registry import load_servers

_LOGGER = init_logger("latch.serve", debug=debug_enabled())


def _load_servers():
    return load_servers().get("servers", [])


def _add(mcp, alias, client, tool):
    qname = f"{alias}__{tool.name}"
    tool_name = tool.name

    async def call(**kw):
        policy = load_policy()
        action, reason = evaluate(qname, policy)
        _LOGGER.debug("policy evaluated tool=%s action=%s", qname, action)

        if action in ("browser", "webauthn"):
            approved, flow_reason = await start_approval_flow(
                qname,
                dict(kw),
                require_webauthn=(action == "webauthn"),
            )
            decision = "allow" if approved else "deny"
            reason = flow_reason
            append(qname, kw, action, decision, reason, action, "mcp")
            if not approved:
                _LOGGER.info("tool denied tool=%s reason=%s", qname, reason)
                return [{"type": "text", "text": reason}]
        elif action == "ask":
            append(qname, kw, action, "deny", f"{reason} (ask not supported in MCP mode, denied)", "policy", "mcp")
            _LOGGER.info("tool denied tool=%s reason=ask-not-supported-in-mcp", qname)
            return [{"type": "text", "text": f'Blocked: tool "{qname}" requires interactive approval (ask), not supported in MCP mode. Update policy to allow/browser/webauthn.'}]
        elif action == "deny":
            append(qname, kw, action, "deny", reason, "policy", "mcp")
            _LOGGER.info("tool denied tool=%s reason=%s", qname, reason)
            return [{"type": "text", "text": f"Blocked by policy: {reason}"}]
        else:
            append(qname, kw, action, "allow", reason, "policy", "mcp")

        return (await client.call_tool(tool_name, kw)).content

    call.__name__ = qname
    mcp.tool(name=qname, description=tool.description or "")(call)


async def _run():
    configured_servers = _load_servers()
    if not configured_servers:
        print(
            "No downstream servers configured in servers.yaml.\n"
            "Run: latch onboard --server-alias fs --server-command npx --server-arg=-y "
            "--server-arg=@modelcontextprotocol/server-filesystem --server-arg=/tmp\n"
            "Or add one manually with: latch add-server <alias> <command> [args...]",
            file=sys.stderr,
        )
        raise SystemExit(1)

    policy = load_policy()
    if policy_uses_ask(policy):
        print(
            "Warning: policy contains action=ask. In MCP mode, ask decisions are denied.\n"
            "Use allow/browser/webauthn for MCP-facing rules (or run: latch onboard to apply MCP-safe defaults).",
            file=sys.stderr,
        )

    mcp = FastMCP("latch-proxy")
    clients: dict = {}

    for s in configured_servers:
        c = Client({"command": s["command"], "args": s.get("args", []), "env": s.get("env") or {}})
        await c.__aenter__()
        clients[s["alias"]] = c

    for alias, client in clients.items():
        for tool in await client.list_tools():
            _add(mcp, alias, client, tool)

    print(f"Latch proxy: {len(clients)} server(s)", file=sys.stderr)
    try:
        await mcp.run_async(transport="stdio")
    finally:
        for c in clients.values():
            await c.__aexit__(None, None, None)


def main():
    asyncio.run(_run())
