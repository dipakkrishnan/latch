import asyncio, sys
import yaml
from fastmcp import FastMCP, Client

from .config import CONFIG_DIR
from .policy import load_policy, evaluate
from .audit import append
from .approval import start_approval_flow


def _load_servers():
    p = CONFIG_DIR / "servers.yaml"
    return (yaml.safe_load(p.read_text()) or {}).get("servers", []) if p.exists() else []


def _add(mcp, alias, client, tool):
    qname = f"{alias}__{tool.name}"
    tool_name = tool.name

    async def call(**kw):
        policy = load_policy()
        action, reason = evaluate(qname, policy)

        if action in ("browser", "webauthn"):
            approved = await start_approval_flow(qname, dict(kw), require_webauthn=(action == "webauthn"))
            decision = "allow" if approved else "deny"
            reason = f"{'Approved' if approved else 'Denied'} in browser ({action})"
            append(qname, kw, action, decision, reason, action, "mcp")
            if not approved:
                return [{"type": "text", "text": f"Denied by user in browser ({action})"}]
        elif action == "ask":
            append(qname, kw, action, "deny", f"{reason} (ask not supported in MCP mode, denied)", "policy", "mcp")
            return [{"type": "text", "text": f'Blocked: tool "{qname}" requires interactive approval (ask), not supported in MCP mode. Update policy to allow/browser/webauthn.'}]
        elif action == "deny":
            append(qname, kw, action, "deny", reason, "policy", "mcp")
            return [{"type": "text", "text": f"Blocked by policy: {reason}"}]
        else:
            append(qname, kw, action, "allow", reason, "policy", "mcp")

        return (await client.call_tool(tool_name, kw)).content

    call.__name__ = qname
    mcp.tool(name=qname, description=tool.description or "")(call)


async def _run():
    mcp = FastMCP("latch-proxy")
    clients: dict = {}

    for s in _load_servers():
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
