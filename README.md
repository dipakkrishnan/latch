# latch

A universal gating and audit layer for AI agents. Latch intercepts agent tool calls, evaluates them against configurable YAML policies, and records every decision — before anything executes.

Works across two integration modes:

| Mode | How it works | Best for |
|---|---|---|
| **Hook** | Pre-tool-use hook process (stdin/stdout) | Claude Code, Codex |
| **MCP Proxy** | Streamable-HTTP MCP proxy between agent and tool servers | OpenClaw, Claude Desktop, any MCP client |

Both modes share the same policy engine, WebAuthn approval flow, and audit log.

## What it does

- **Policy enforcement** — define per-tool rules (allow, deny, ask, browser, or webauthn) via YAML
- **WebAuthn gating** — require biometric/passkey approval for sensitive actions
- **MCP proxy** — presents as an MCP server to the agent while proxying downstream MCP servers, intercepting `tools/call` before forwarding
- **Audit log** — every tool call, its inputs, and the decision are recorded
- **Agent attribution** — auto-detects the calling agent (Claude Code, Codex, OpenClaw) or set it explicitly
- **Web dashboard** — manage policies, enroll passkeys, and browse audit logs

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dipakkrishnan/latch/main/scripts/install-latch.sh | sh
latch init
```

Alternative:
```bash
pipx install latch-agent
latch init
```

## Quick Start

### Hook mode (Claude Code)

Add latch as a pre-tool-use hook in your Claude Code `settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [{ "command": "latch-hook" }]
  }
}
```

### Hook mode (Codex)

Set up latch as a pre-tool-use hook in your Codex configuration, pointing to `latch-hook`.

### MCP proxy mode

Add a downstream server to `~/.agent-2fa/servers.yaml`:

```yaml
servers:
  - alias: filesystem
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

Start the proxy:

```bash
latch serve
```

Then configure your agent to use `latch-serve` as its MCP server. Tool names are namespaced as `alias__toolName`.

When a tool requires approval, latch returns an approval URL to the agent. The agent shows the URL in chat, then calls `latch__check_approval` which blocks until the user approves or denies:

```
Agent → tools/call → Latch Proxy → Policy Engine
  ├─ allow    → forward to downstream MCP server
  ├─ deny     → return error to agent
  └─ browser/webauthn → return approval URL → agent shows in chat
       → agent calls check_approval (blocks) → user approves → forward → return result
```

### OpenClaw + Docker (sidecar)

The recommended way to run latch with OpenClaw is as a Docker sidecar. This gives you a Cloudflare tunnel for remote approval (e.g. from WhatsApp).

**1. Start the latch container:**

```bash
docker compose up -d latch
```

This starts latch on port 8100 (MCP) and 8200 (approval), with a Cloudflare quick tunnel for remote approval URLs.

**2. Install mcporter in the OpenClaw container:**

```bash
# Inside the OpenClaw container:
npm install -g mcporter
```

**3. Configure mcporter to point at latch:**

Create `~/.mcporter/mcporter.json` (inside the OpenClaw container):

```json
{
  "mcpServers": {
    "latch": {
      "url": "http://host.docker.internal:8100/mcp"
    }
  }
}
```

**4. Verify the connection:**

```bash
mcporter list
# Should show: latch (N tools)
```

**5. Enroll a passkey (for WebAuthn approval):**

```bash
latch enroll --remote
```

Open the enrollment URL on your phone and register a passkey.

**6. Test from OpenClaw chat:**

In the OpenClaw Control UI or WhatsApp, ask the agent to call a latch tool:

> Use mcporter to call latch.your_tool

The agent will show the approval URL in chat. Open the link, approve with your passkey, and the result flows back to the chat.

### OpenClaw plugin (local mode)

For local (non-Docker) setups:

```bash
openclaw plugins install openclaw-latch
```

The plugin detects `LATCH_URL` for network mode, or spawns `latch-serve` locally.

## Policy format

Edit `~/.agent-2fa/policy.yaml`. Rules are matched top-to-bottom:

```yaml
defaultAction: allow
rules:
  - match: { tool: Bash }
    action: ask
  - match: { tool: 'Edit|Write|NotebookEdit' }
    action: ask
  - match: { tool: 'Read|Glob|Grep' }
    action: allow
  - match: { tool: '*__send_*' }
    action: webauthn
  - match: { tool: '*__delete_*' }
    action: webauthn
```

Supported actions: `allow`, `deny`, `ask`, `browser` (browser-based approval), `webauthn` (passkey required).

## CLI

```
latch init       # Initialize config directory
latch hook       # Run as stdin/stdout hook
latch serve      # Run as MCP proxy server
latch dashboard  # Launch web dashboard
latch enroll     # Enroll a WebAuthn passkey
latch status     # Show config summary
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_2FA_DIR` | `~/.agent-2fa` | Config directory path |
| `AGENT_2FA_CLIENT` | auto-detected | Override client detection |
| `AGENT_2FA_AGENT_ID` | auto-generated | Set agent identity for audit entries |
| `LATCH_HOOK_DEBUG` | `false` | Enable debug logging for hook mode |
| `LATCH_APPROVAL_PORT` | random | Port for approval HTTP server |
| `LATCH_MCP_TRANSPORT` | `stdio` | MCP transport (`stdio`, `streamable-http`, `sse`) |
| `LATCH_MCP_HOST` | `127.0.0.1` | MCP HTTP bind host |
| `LATCH_MCP_PORT` | `8000` | MCP HTTP bind port |
| `LATCH_MCP_PATH` | `/mcp` | MCP HTTP path |

## Development

```bash
cd py
uv sync
uv run pytest
```
