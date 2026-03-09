# latch

A universal gating and audit layer for AI agents. Latch intercepts agent tool calls, evaluates them against configurable YAML policies, and records every decision — before anything executes.

Works across two integration modes:

| Mode | How it works | Best for |
|---|---|---|
| **Hook** | Pre-tool-use hook process (stdin/stdout) | Claude Code, Codex, OpenClaw |
| **MCP Proxy** | stdio MCP proxy between agent and tool servers | Claude Desktop, any MCP client |

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
latch setup
```

Alternative:
```bash
pipx install latch-agent
latch setup
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

Add a downstream server:

Edit `~/.agent-2fa/servers.yaml`:

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

```
Agent → tools/call → Latch Proxy → Policy Engine
  ├─ allow    → forward to downstream MCP server
  ├─ deny     → return error to agent
  └─ webauthn → open browser → passkey approval → forward (or deny)
```

### OpenClaw plugin

```bash
openclaw plugins install openclaw-latch
```

The plugin automatically installs `latch-agent`, runs `latch init`, and registers `latch-serve` as an MCP server.

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
latch setup      # Guided setup wizard
latch status     # Show config summary
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_2FA_DIR` | `~/.agent-2fa` | Config directory path |
| `AGENT_2FA_CLIENT` | auto-detected | Override client detection |
| `AGENT_2FA_AGENT_ID` | auto-generated | Set agent identity for audit entries |
| `LATCH_HOOK_DEBUG` | `false` | Enable debug logging for hook mode |

## Development

```bash
cd py
uv sync
uv run pytest
```
