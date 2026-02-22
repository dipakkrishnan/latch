# latch

A universal gating and audit layer for AI agents. Latch intercepts agent tool calls, evaluates them against configurable policies, and records every decision — before anything executes.

Works with Claude Code, Codex, OpenClaw, and any agent that supports pre-tool-use hooks.

## What it does

- **Policy enforcement** — define per-tool rules (allow, deny, ask, or require passkey) via a dashboard UI
- **WebAuthn gating** — require biometric approval for sensitive actions
- **Audit log** — every tool call, its inputs, and the decision are recorded with agent identity
- **Agent attribution** — automatically detects the calling agent (or set it explicitly) to tag audit entries

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

## Configuring your agent

Point your agent's pre-tool-use hook at the latch entry point. For Claude Code, add to your `settings.json`:

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

## Commands

```bash
npm run dashboard          # start dashboard and open browser
npm run dashboard:no-open  # start dashboard without opening browser
npm run dev:ui             # run Vite UI dev server
npm run test               # run full test suite
npm run smoke              # build + dashboard smoke tests
npm run smoke:e2e          # API + hook integration checks
```
