# latch-agent

Universal gating and audit layer for AI agents. Intercepts tool calls, evaluates them against YAML policies, logs decisions, and supports WebAuthn approval flows.

## Quick Start

```bash
curl -fsSL https://raw.githubusercontent.com/dipakkrishnan/latch/main/scripts/install-latch.sh | sh
latch init
```

Alternative:
```bash
pipx install latch-agent
latch init
```

## OpenClaw Integration

```bash
openclaw plugins install openclaw-latch
```

The plugin automatically installs `latch-agent`, runs `latch init`, and registers `latch-serve` as an MCP server.

## Claude Code Integration

Add latch as a hook in your Claude Code settings:

```json
{
  "hooks": {
    "PreToolUse": [{ "command": "latch-hook" }]
  }
}
```

## Codex Integration

Set up latch as a pre-tool-use hook in your Codex configuration, pointing to `latch-hook`.

## Policy Format

Edit `~/.agent-2fa/policy.yaml`:

```yaml
defaultAction: allow
rules:
  - match: { tool: Bash }
    action: ask
  - match: { tool: 'Edit|Write|NotebookEdit' }
    action: ask
  - match: { tool: 'Read|Glob|Grep' }
    action: allow
```

Actions: `allow`, `deny`, `ask`, `browser` (browser-based approval), `webauthn` (passkey required).

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_2FA_DIR` | `~/.agent-2fa` | Config directory path |
| `AGENT_2FA_CLIENT` | auto-detected | Override client detection |
| `LATCH_HOOK_DEBUG` | `false` | Enable debug logging for hook mode |

## CLI Commands

```
latch init       # Initialize config directory
latch hook       # Run as stdin/stdout hook
latch serve      # Run as MCP proxy server
latch dashboard  # Launch web dashboard
latch enroll     # Enroll a WebAuthn passkey
latch status     # Show config summary
```

## Development

```bash
cd py
uv sync
uv run pytest
```
