# openclaw-latch

Latch security gate plugin for OpenClaw. Adds policy-based tool gating with audit logging and optional WebAuthn approval flows.

## Install

Local/linked install (recommended while developing this repo):

```bash
openclaw plugins install -l ./openclaw-plugin
openclaw plugins doctor
openclaw plugins list
```

Package-name install (use after publishing `openclaw-latch`):

```
openclaw plugins install openclaw-latch
```

This will:
1. Install the `latch-agent` Python package (via pipx or pip)
2. Run `latch init` to create the default config at `~/.agent-2fa/`
3. Register `latch-serve` as an MCP server in OpenClaw

## Requirements

- Python 3.10+
- [pipx](https://pypa.github.io/pipx/) (recommended) or pip

## Manual Setup

If automatic installation doesn't work:

```bash
pipx install latch-agent
latch init
```

Then add to your OpenClaw MCP config:

```json
{
  "mcpServers": {
    "latch": {
      "command": "latch-serve",
      "args": []
    }
  }
}
```

## Troubleshooting

- `latch-serve not found`: run `pipx install latch-agent && latch init`
- `pipx` unavailable: install `pipx` or ensure `pip` is on your PATH
- plugin installed but not active: run `openclaw plugins doctor` and confirm the plugin id `openclaw-latch`
- MCP registration issues: use the JSON snippet printed by the plugin for manual MCP setup

## Configuration

Edit `~/.agent-2fa/policy.yaml` to customize tool gating rules. See the [latch-agent docs](https://github.com/dipakkrishnan/latch) for policy format details.
