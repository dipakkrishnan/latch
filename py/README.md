# latch-agent

Universal gating and audit layer for AI agents. Intercepts tool calls, evaluates them against YAML policies, logs decisions, and supports WebAuthn approval flows.

Security defaults:
- Hook errors are fail-closed (tool calls are denied on hook exceptions).
- Browser/WebAuthn approval requests time out and deny by default.

## Quick Start

```bash
pip install latch-agent
latch init
```

## OpenClaw Integration

```bash
openclaw plugins install -l ./openclaw-plugin
openclaw plugins doctor
openclaw plugins list
```

The plugin automatically installs `latch-agent`, runs `latch init`, and registers `latch-serve` as an MCP server.
After the plugin is published, you can also install by package name with `openclaw plugins install openclaw-latch`.

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
| `LATCH_DEBUG` | `false` | Enable debug logging for all Python latch services |
| `LATCH_APPROVAL_TIMEOUT_SEC` | `120` | Approval flow timeout in seconds; timeout denies request |

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
