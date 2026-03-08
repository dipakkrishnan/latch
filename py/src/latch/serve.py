import asyncio, sys
import yaml
from fastmcp import FastMCP, Client

from .config import CONFIG_DIR
from .policy import load_policy, evaluate
from .audit import append
from .approval import ApprovalServer
from .tunnel import start_tunnel, stop_tunnel


def _load_servers():
    p = CONFIG_DIR / "servers.yaml"
    return (yaml.safe_load(p.read_text()) or {}).get("servers", []) if p.exists() else []


def _add(mcp, alias, client, tool, approval_server):
    qname = f"{alias}__{tool.name}"
    tool_name = tool.name

    async def call(**kw):
        policy = load_policy()
        action, reason = evaluate(qname, policy)

        if action in ("browser", "webauthn", "ask"):
            require_webauthn = action == "webauthn"
            approval_id, url = approval_server.create_request(qname, dict(kw), require_webauthn=require_webauthn)
            sys.stderr.write(f"Approval URL: {url}\n")

            # Return URL to agent so it can relay to user
            prompt_text = f"Approval required for tool \"{qname}\". Open to approve: {url}"

            # Start waiting for decision in background, but first notify agent
            decision_task = asyncio.create_task(approval_server.wait_for_decision(approval_id))

            # If no tunnel, also try opening browser locally
            if not approval_server._tunnel_url:
                import webbrowser
                webbrowser.open(url)

            approved = await decision_task
            decision = "allow" if approved else "deny"
            reason_text = f"{'Approved' if approved else 'Denied'} via approval flow ({action})"
            append(qname, kw, action, decision, reason_text, action, "mcp")
            if not approved:
                return [{"type": "text", "text": f"Denied by user ({action})"}]
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

    # Start persistent approval server
    approval_server = ApprovalServer()
    await approval_server.start()

    # Start Cloudflare tunnel
    tunnel_url = await start_tunnel(approval_server.port)
    approval_server.set_tunnel_url(tunnel_url)

    for s in _load_servers():
        c = Client({"command": s["command"], "args": s.get("args", []), "env": s.get("env") or {}})
        await c.__aenter__()
        clients[s["alias"]] = c

    for alias, client in clients.items():
        for tool in await client.list_tools():
            _add(mcp, alias, client, tool, approval_server)

    print(f"Latch proxy: {len(clients)} server(s)", file=sys.stderr)
    if tunnel_url:
        print(f"Tunnel: {tunnel_url}", file=sys.stderr)
    try:
        await mcp.run_async(transport="stdio")
    finally:
        for c in clients.values():
            await c.__aexit__(None, None, None)
        await approval_server.stop()
        await stop_tunnel()


def main():
    asyncio.run(_run())
