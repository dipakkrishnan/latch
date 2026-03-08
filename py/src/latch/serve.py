import asyncio, sys
import yaml
from fastmcp import FastMCP, Client

from .config import (
    CONFIG_DIR,
    LATCH_MCP_HOST,
    LATCH_MCP_PATH,
    LATCH_MCP_PORT,
    LATCH_MCP_TRANSPORT,
)
from .policy import load_policy, evaluate
from .audit import append
from .approval import ApprovalServer
from .tunnel import start_tunnel, stop_tunnel, get_tunnel_url


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

            # Start waiting for decision in background, but first notify agent
            decision_task = asyncio.create_task(approval_server.wait_for_decision(approval_id))

            # If no tunnel, also try opening browser locally
            if not approval_server.has_tunnel:
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

    for s in _load_servers():
        c = Client({"command": s["command"], "args": s.get("args", []), "env": s.get("env") or {}})
        await c.__aenter__()
        clients[s["alias"]] = c

    for alias, client in clients.items():
        for tool in await client.list_tools():
            _add(mcp, alias, client, tool, approval_server)

    transport = (LATCH_MCP_TRANSPORT or "stdio").strip().lower()
    print(f"Latch proxy: {len(clients)} server(s)", file=sys.stderr)
    print(f"MCP transport: {transport}", file=sys.stderr)
    if transport != "stdio":
        endpoint = f"http://{LATCH_MCP_HOST}:{LATCH_MCP_PORT}{LATCH_MCP_PATH}"
        print(f"MCP endpoint: {endpoint}", file=sys.stderr)
    if get_tunnel_url():
        print(f"Approval tunnel: {get_tunnel_url()}", file=sys.stderr)
    try:
        if transport == "stdio":
            await mcp.run_async(transport="stdio")
        elif transport in {"http", "streamable-http", "sse"}:
            run_kwargs = {
                "transport": transport,
                "host": LATCH_MCP_HOST,
                "port": LATCH_MCP_PORT,
            }
            if transport in {"http", "streamable-http"}:
                run_kwargs["path"] = LATCH_MCP_PATH
            await mcp.run_async(**run_kwargs)
        else:
            raise ValueError(f"Unsupported MCP transport: {transport}")
    finally:
        for c in clients.values():
            await c.__aexit__(None, None, None)
        await approval_server.stop()
        await stop_tunnel()


def main():
    asyncio.run(_run())
