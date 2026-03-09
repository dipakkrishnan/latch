import asyncio, json, sys
import yaml
from fastmcp import FastMCP, Client
from fastmcp.client.transports import StdioTransport

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


def _add_approval_tools(mcp, approval_server):
    """Register the check_approval and pending_approvals tools."""

    async def check_approval(approval_id: str) -> list:
        """Check the status of a pending approval. Returns the result if decided, or 'pending' if still waiting.

        Call this after a tool returns an approval URL. Pass the approval_id from that response.
        If approved, the original tool call is automatically executed and the result returned."""
        session = approval_server._sessions.get(approval_id)
        if not session:
            return [{"type": "text", "text": f"Approval {approval_id} not found (expired or already resolved)."}]

        if not session["event"].is_set():
            return [{"type": "text", "text": "pending"}]

        approved = session["approved"]
        tool_name = session["tool"]
        tool_args = session["args"]
        approval_server._sessions.pop(approval_id, None)

        if not approved:
            append(tool_name, tool_args, "browser", "deny", "Denied by user", "browser", "mcp")
            return [{"type": "text", "text": f"Denied by user."}]

        # Approved — execute the original tool call
        append(tool_name, tool_args, "browser", "allow", "Approved by user", "browser", "mcp")

        # Find the downstream client and call the real tool
        alias, _, downstream_tool = tool_name.partition("__")
        client = approval_server._clients.get(alias)
        if not client:
            return [{"type": "text", "text": f"Approved, but downstream server '{alias}' not found."}]

        result = await client.call_tool(downstream_tool, tool_args)
        return result.content

    check_approval.__name__ = "latch__check_approval"
    mcp.tool(
        name="latch__check_approval",
        description="Check status of a pending tool approval. Pass the approval_id returned when a tool requires approval. Returns 'pending', the tool result (if approved), or a denial message.",
    )(check_approval)


def _add(mcp, alias, client, tool, approval_server):
    qname = f"{alias}__{tool.name}"
    tool_name = tool.name

    async def call(input: dict | None = None):
        kw = input if isinstance(input, dict) else {}
        policy = load_policy()
        action, reason = evaluate(qname, policy)

        if action in ("browser", "webauthn", "ask"):
            require_webauthn = action == "webauthn"
            approval_id, url = approval_server.create_request(qname, dict(kw), require_webauthn=require_webauthn)

            # If no tunnel, also try opening browser locally
            if not approval_server.has_tunnel:
                import webbrowser
                webbrowser.open(url)

            # Return the URL immediately — agent shows it to user, then polls check_approval
            return [{"type": "text", "text": json.dumps({
                "status": "approval_required",
                "approval_id": approval_id,
                "url": url,
                "tool": qname,
                "message": f"Approval required for {qname}. Open to approve: {url}",
                "next": f'Call latch__check_approval with approval_id="{approval_id}" to check the result.',
            })}]
        elif action == "deny":
            append(qname, kw, action, "deny", reason, "policy", "mcp")
            return [{"type": "text", "text": f"Blocked by policy: {reason}"}]
        else:
            append(qname, kw, action, "allow", reason, "policy", "mcp")

        return (await client.call_tool(tool_name, kw)).content

    call.__name__ = qname
    desc = tool.description or ""
    if desc:
        desc += "\n\n"
    desc += "Proxy wrapper. Pass downstream tool args in the `input` object."
    mcp.tool(name=qname, description=desc)(call)


async def _run():
    mcp = FastMCP("latch-proxy")
    clients: dict = {}

    # Start persistent approval server
    approval_server = ApprovalServer()
    await approval_server.start()

    # Start Cloudflare tunnel
    tunnel_url = await start_tunnel(approval_server.port)

    for s in _load_servers():
        transport = StdioTransport(
            command=s["command"],
            args=s.get("args", []),
            env=s.get("env") or {},
        )
        c = Client(transport)
        await c.__aenter__()
        clients[s["alias"]] = c

    # Store clients on the approval server so check_approval can call downstream tools
    approval_server._clients = clients

    for alias, client in clients.items():
        for tool in await client.list_tools():
            _add(mcp, alias, client, tool, approval_server)

    # Register approval check tool
    _add_approval_tools(mcp, approval_server)

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
