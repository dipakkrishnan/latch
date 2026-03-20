# Clawdian Approver V2 - Build Plan

## 1. Goal
Ship a production-ready `clawdian-approver` service that bridges OpenClaw exec approvals to Latch 2FA (WebAuthn), with simple setup for both Docker and local installs.

## 2. What This Adds
1. A new long-running service: `clawdian-approver`.
2. Gateway operator client behavior:
   1. Subscribe to `exec.approval.requested`.
   2. Call Latch for approval challenge creation.
   3. Resolve back via `exec.approval.resolve`.
3. End-user flow:
   1. Approval request appears in user channel (e.g., WhatsApp/UI) with Latch link.
   2. User passkey-verifies in Latch.
   3. OpenClaw command proceeds/denies.

## 3. Core Principles
1. Keep OpenClaw `exec-approvals` enabled as final host guardrail.
2. Latch becomes identity-bound approval decision plane.
3. Fail safe:
   1. If approver is down, requests remain pending or fail closed (never auto-allow).
4. Idempotent resolution:
   1. Exactly-once semantic at business level, at-least-once transport with dedupe.

## 4. Deliverables
1. `clawdian-approver` runtime in Python package.
2. Config model and env schema.
3. Reliable event loop, reconnection, dedupe, timeout handling.
4. Latch native gating API support (if missing pieces remain).
5. Installer/setup wizard support (`latch setup openclaw` path).
6. Docker sidecar + local daemon deployment targets.
7. Tests (unit + integration + fault scenarios).
8. Runbook + troubleshooting docs.

## 5. Architecture Tasks

### 5.1 New Service Module
1. Add `py/src/latch/approver.py`:
   1. Gateway WS client.
   2. Event router for `exec.approval.requested`.
   3. Latch API client wrapper.
   4. Resolver client for `exec.approval.resolve`.
2. Add CLI entrypoint:
   1. `clawdian-approver` console script.
   2. Subcommands: `run`, `check`, `version`.

### 5.2 Event Handling + State
1. Parse/validate approval event payload (approval id, command context, session context).
2. Build correlation model:
   1. `approval_id`
   2. `request_hash`
   3. `session_key/channel/to/agent_id`
3. Add in-memory dedupe + optional disk-backed cache for restart recovery.
4. Add configurable timeout policy:
   1. Pending expiry.
   2. Retry budget.

### 5.3 Latch API Contract
1. Ensure/implement:
   1. `POST /v1/gate/native` returns `allow|deny|pending`.
   2. `GET /v1/gate/native/{approvalId}` returns terminal/pending state.
2. Include session routing fields in requests.
3. Include operator metadata for audit attribution.

### 5.4 Resolver Flow
1. On `allow`: call `exec.approval.resolve` with configured decision mode:
   1. Default `allow-once`.
2. On `deny`: call resolve deny.
3. On timeout/error:
   1. Resolve deny or leave pending based on strict policy flag (default deny).
4. Ensure idempotent resolve (ignore already-resolved responses).

## 6. Resilience Tasks
1. WS reconnect with exponential backoff + jitter.
2. Heartbeat/ping checks and stale-connection detection.
3. Circuit breaker for Latch API unavailability.
4. Structured logging and reason codes for each decision path.
5. Metrics:
   1. events received
   2. pending created
   3. allow/deny resolved
   4. timeout/error counts
   5. reconnect attempts
6. Dead-letter handling:
   1. Persist failed events for manual replay.

## 7. Security Tasks
1. Operator token scope validation at startup (`operator.approvals` required).
2. Secrets handling:
   1. Env-only or mounted file secrets.
   2. Never log tokens or passkey payloads.
3. TLS verification for Gateway/Latch URLs.
4. Input sanitization on event payload before forwarding.
5. Optional request signing between approver and latch (future-ready hook).

## 8. UX + Setup Tasks

### 8.1 Setup TUI (MVP)
Single command: `latch setup openclaw`. User provides Gateway token, wizard does everything else.

1. Detect Gateway:
   1. Auto-probe `ws://localhost:18789`, fall back to prompt.
   2. Validate connection with a quick WS open.
2. Collect token:
   1. Prompt for Gateway operator token (masked input).
   2. That's it — Latch URL/token are internal, not user-facing.
3. Start Latch (if not running):
   1. Auto-start Latch server (Docker or local subprocess).
   2. Wait for health check to pass.
4. Device pairing (fully automated):
   1. Generate Ed25519 keypair (or load existing).
   2. Attempt Gateway connect.
   3. If pairing required → auto-approve via Gateway Control API if local, otherwise open Control UI in browser and poll with spinner until approved.
   4. Persist device token from `hello-ok`.
5. Passkey enrollment (inline):
   1. Check if Latch has enrolled credentials.
   2. If not → open enrollment page in browser, wait with spinner until complete.
6. Smoke test:
   1. Send a test approval through the full pipeline.
   2. Print "Setup complete. Approver running."
7. Start approver as background daemon.

**User effort: one command, one token paste, one passkey tap.**

### 8.2 Deployment Targets
1. Docker:
   1. Add `clawdian-approver` service in `docker-compose.yml`.
   2. Add healthcheck and restart policy.
2. Local:
   1. macOS `launchd` installer script.
   2. Linux `systemd --user` unit installer script.
   3. `clawdian-approver check` command for diagnostics.

### 8.3 User-Facing Flow
1. Standardize approval message text for chat channels.
2. Ensure one clear link to passkey approval page.
3. Return concise completion message after resolve.

## 9. Test Plan

### 9.1 Unit Tests
1. Event parsing/validation.
2. Latch client success/failure paths.
3. Resolve idempotency and dedupe behavior.
4. Timeout and retry policies.

### 9.2 Integration Tests
1. Mock Gateway WS + mock Latch API end-to-end.
2. Happy path:
   1. requested -> pending -> allow -> resolve success.
3. Deny path.
4. Latch timeout path.
5. Gateway reconnect during pending request.
6. Duplicate event delivery.

### 9.3 System Tests (Docker Compose)
1. OpenClaw + latch + clawdian-approver stack.
2. Trigger real `tools.exec` requiring approval.
3. Verify:
   1. approval URL delivered
   2. passkey approval unblocks command
   3. logs and audits consistent across systems.

## 10. Docs Tasks
1. Add architecture section to root `README.md`:
   1. operator client vs channel explanation.
2. Add quickstart for:
   1. Docker sidecar mode.
   2. Local daemon mode.
3. Add troubleshooting:
   1. token scope mismatch
   2. WS disconnect loops
   3. approval stays pending
   4. duplicate approvals

## 11. MVP Definition

MVP = **2FA approval flow + setup TUI**. A user can:
1. Run `latch setup openclaw` → guided pairing + enrollment.
2. Start approver → agent tool calls require passkey approval.
3. Approve/deny via Latch URL with WebAuthn.

### MVP scope (in):
- Gateway WS connect + device auth (done).
- `POST /v1/gate/native` + `GET /v1/gate/native/{id}` in Latch server.
- Clawdian approver service with reconnect + dedupe.
- Setup TUI: config collection, device pairing, enrollment check, smoke test.
- Single deployment mode (local process, Docker stretch).

### MVP scope (out):
- Fault injection / circuit breaker.
- Dead-letter / replay persistence.
- launchd / systemd installers.
- Audit trail cross-linking.
- Dashboard policy integration.

## 12. Milestones
1. Milestone A — Gateway connect (done):
   1. Device auth, v2 signing, connect handshake.
   2. Event subscription + reconnect loop.
2. Milestone B — Latch native gate API:
   1. `POST /v1/gate/native` → create approval session, return pending + URL.
   2. `GET /v1/gate/native/{id}` → poll session state.
   3. End-to-end: requested → pending → passkey → allow/deny → resolve.
3. Milestone C — Setup TUI:
   1. Interactive wizard with config, pairing, enrollment, smoke test.
   2. `clawdian-approver check` diagnostics command.
4. Milestone D (post-MVP):
   1. Docker sidecar + compose integration.
   2. Hardening: circuit breaker, dead-letter, observability.
   3. launchd / systemd installers.

## 13. Acceptance Criteria (MVP)
1. `latch setup openclaw` gets a new user from zero to working approver.
2. Exec approval events route through Latch passkey flow and resolve back to OpenClaw.
3. Service reconnects automatically on transient failures, never auto-allows.

## 14. Open Questions
1. Default unresolved behavior at timeout:
   1. explicit deny vs leave pending for human fallback.
2. Whether to ship chat message push from approver directly or keep it solely in latch.
3. Should TUI use textual/rich or keep it simple with plain prompts?
