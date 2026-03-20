# core

Fresh implementation area for `clawdian-approver`.

This skeleton provides:
1. Gateway event listener for `exec.approval.requested`.
2. Latch native gate authorize + poll flow.
3. Gateway approval resolution (`exec.approval.resolve`).

Run:

```bash
python -m core.clawdian_approver.main run
```

Required environment variables:
1. `OPENCLAW_GATEWAY_WS_URL`
2. `OPENCLAW_GATEWAY_TOKEN`
3. `LATCH_BASE_URL`
4. `LATCH_TOKEN`

Optional:
1. `CLAWDIAN_ALLOW_DECISION` (`allow-once` or `allow-always`, default `allow-once`)
2. `CLAWDIAN_POLL_INTERVAL_SECONDS` (default `2`)
3. `CLAWDIAN_POLL_TIMEOUT_SECONDS` (default `300`)
4. `CLAWDIAN_STRICT_DENY_ON_ERROR` (`true`/`false`, default `true`)
5. `CLAWDIAN_DEBUG_FRAMES` (`true`/`false`, default `false`)
6. `CLAWDIAN_SCOPES` (comma list, default `operator.read,operator.write,operator.approvals`)
7. `CLAWDIAN_CLIENT_ID` (default `cli`)
8. `CLAWDIAN_CLIENT_MODE` (default `operator`)
9. `CLAWDIAN_CLIENT_MODE_CANDIDATES` (default `operator,control,cli,web,desktop,service,bot`)
10. `CLAWDIAN_CLIENT_VERSION` (default `0.1.0`)
11. `CLAWDIAN_CLIENT_PLATFORM` (default from OS)
12. `CLAWDIAN_USER_AGENT` (default `<client_id>/<client_version>`)
13. `CLAWDIAN_DEVICE_KEY_PATH` (default `~/.clawdian-approver/device_ed25519.pem`)
