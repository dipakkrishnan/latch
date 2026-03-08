# latch

Latch is a local policy gate for agent/tool commands with TOTP approvals and audit logging.

## What it does

- Evaluates incoming commands against regex-based policy rules (`allow`, `deny`, `approve`).
- Requires a valid 6-digit TOTP code when a command resolves to `approve`.
- Sends approval prompts through your OpenClaw hook endpoint.
- Stores an append-only JSONL audit trail for every decision.

## Install

```bash
uv sync
```

## First-time setup

```bash
uv run latch setup
```

`setup` will:

- Auto-detect your OpenClaw gateway URL/token (or prompt for token).
- Generate a TOTP secret.
- Show QR/manual secret for enrollment in your authenticator app.
- Verify one code and store the secret locally.

## Run the approval server

```bash
uv run latch run
```

Default bind: `127.0.0.1:18890` (override with `LATCH_PORT`)

Endpoint:

- `POST /approve` with `{"command": "...", "tool_input": {...}}`
- `GET/POST /callback/<approval_id>` approval page + code submit

OpenClaw prerequisite:

- `hooks.enabled` must be `true` and `hooks.token` must be set in your OpenClaw config so `POST /hooks/agent` accepts latch requests.

Decision responses:

- `{"decision":"allow-once","reason":"..."}`
- `{"decision":"deny","reason":"..."}`

## Run Latch inside your OpenClaw Docker container

One-time setup is now wired via `/Users/anupbottu/openclaw/docker-compose.override.yml`.

From `/Users/anupbottu/openclaw`:

```bash
docker compose up -d
docker compose exec openclaw-gateway latch setup
```

After that, keep using:

```bash
docker compose up -d
```

Notes:

- Latch runs in the `openclaw-gateway` container on `0.0.0.0:18890`.
- Host access is `http://127.0.0.1:18890/approve`.
- Latch state persists in `${OPENCLAW_CONFIG_DIR}/latch` mounted at `/home/node/.latch`.
- The container auto-installs the `latch-approval-gate` OpenClaw plugin on startup.
- That plugin hooks `before_tool_call` so agent tool calls are routed through Latch `/approve` first.
- After pulling these changes, rebuild once: `docker compose build --no-cache openclaw-gateway openclaw-cli`.

## Policy

Policy file: `~/.latch/policy.yaml`

Default behavior:

- Safe commands: allow
- Destructive commands: deny
- Everything else: approve (requires TOTP)

Example:

```yaml
defaultAction: approve
rules:
  - match: {tool: '(ls|pwd|whoami|cat|head|tail|echo|date|env)'}
    action: allow
  - match: {tool: '(rm|chmod|chown|kill|shutdown|reboot)'}
    action: deny
```

Rules are evaluated top-to-bottom; first match wins.

## CLI commands

```bash
uv run latch setup
uv run latch run
uv run latch policy
uv run latch audit
uv run latch status
uv run latch reset
```

## Local files

By default, latch stores state under `~/.latch` (override with `LATCH_DIR`):

- `config.yaml`
- `totp_secret.key`
- `policy.yaml`
- `audit.jsonl`

Optional runtime env:

- `LATCH_HOST` (server bind host; default `127.0.0.1`)
- `LATCH_PORT` (server bind port; default `18890`)
- `LATCH_APPROVAL_BASE_URL` (public/base URL used in approval links)

## Test

```bash
make test
```
