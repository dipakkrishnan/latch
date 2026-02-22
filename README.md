# latch

A universal gating and audit layer for AI agents. Latch intercepts agent tool calls, evaluates them against configurable policies, and records every decision — before anything executes.

Works across two integration modes:

| Mode | How it works | Best for |
|---|---|---|
| **Hook** | Pre-tool-use hook process | Claude Code, Codex, OpenClaw |
| **MCP Proxy** | stdio MCP proxy between agent and tool servers | Claude Desktop, any MCP client |

Both modes share the same policy engine, WebAuthn approval flow, session cache, and audit log.

## What it does

- **Policy enforcement** — define per-tool rules (allow, deny, ask, or require passkey) via a dashboard UI
- **WebAuthn gating** — require biometric approval for sensitive actions; approvals are cached per-session so you're not interrupted on every call
- **MCP proxy** — presents as an MCP server to the agent while proxying downstream MCP servers, intercepting `tools/call` before forwarding
- **Audit log** — every tool call, its inputs, and the decision are recorded with agent identity
- **Agent attribution** — auto-detects the calling agent (or set it explicitly) to tag audit entries

## Quick Start

1. Install deps:
```bash
npm install
```
2. Build server + dashboard UI:
```bash
npm run build
```
3. Run dashboard:
```bash
npm run dashboard
```

Open `http://localhost:2222` to manage policies, enroll passkeys, and view the audit log.

> Use `http://localhost:2222` for WebAuthn enrollment — `127.0.0.1` will not work.

## Integration

### Hook mode

Point your agent's pre-tool-use hook at the latch entry point. For Claude Code, add to `settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": ".*",
        "hooks": [{ "type": "command", "command": "npx tsx /path/to/latch/src/hook.ts" }]
      }
    ]
  }
}
```

### MCP proxy mode

Latch acts as an MCP server (stdio) to your agent while proxying one or more downstream MCP servers. The agent sees a unified, namespaced tool list; every `tools/call` is evaluated against policy before being forwarded.

```
Agent → tools/call → Latch Proxy → Policy Engine
  ├─ allow  → forward to downstream MCP server
  ├─ deny   → return error to agent
  └─ webauthn → open browser → biometric approval → forward (or deny on timeout)
```

Add a downstream server:
```bash
npx tsx src/index.ts add-server filesystem npx -y @modelcontextprotocol/server-filesystem /tmp
```

Start the proxy:
```bash
npx tsx src/index.ts serve
```

Then configure your agent to use latch as its MCP server.

## Agent Attribution

Set `AGENT_2FA_AGENT_ID` to tag audit entries with a specific agent identity:

```bash
AGENT_2FA_AGENT_ID=agent-1 npm run dashboard
```

Latch also auto-detects the client from environment signals (Claude Code, Codex, OpenClaw).

## Dashboard

| Section | What you can do |
|---|---|
| `#/policy` | Add, edit, reorder, and delete per-tool rules |
| `#/credentials` | Enroll and manage WebAuthn passkeys |
| `#/audit` | Browse all decisions with tool-name and outcome filters |

## Policy format

Rules are matched top-to-bottom. Supported actions: `allow`, `deny`, `ask`, `webauthn`.

```yaml
defaultAction: allow
rules:
  - match:
      tool: "*__send_*"
    action: webauthn
    session:
      duration: 10
      scope: tool
  - match:
      tool: "*__delete_*"
    action: webauthn
  - match:
      tool: "Bash"
    action: ask
```

Tool names in MCP proxy mode are namespaced as `serverName__toolName`.

## Commands

```bash
npm run dashboard          # start dashboard and open browser
npm run dashboard:no-open  # start dashboard without opening browser
npm run dev:ui             # run Vite UI dev server
npm run test               # run full test suite
npm run smoke              # build + dashboard smoke tests
npm run smoke:e2e          # API + hook integration checks
```
