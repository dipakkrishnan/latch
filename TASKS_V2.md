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

### 8.1 Wizard
1. Add `latch setup openclaw` flow in CLI:
   1. Detect Docker vs local OpenClaw.
   2. Configure `approvals.exec` in OpenClaw.
   3. Collect gateway/latch endpoints and tokens.
   4. Install and start approver service.
   5. Run smoke test.

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

## 11. Suggested Milestones
1. Milestone A (2-3 days):
   1. Skeleton approver service + config + CLI.
   2. Basic WS subscribe + manual resolve command.
2. Milestone B (3-5 days):
   1. Latch bridge + end-to-end pending/allow/deny.
   2. Dedupe + retry + reconnect hardening.
3. Milestone C (2-4 days):
   1. Docker/local installers + wizard integration.
   2. Smoke tests + docs.
4. Milestone D (2-3 days):
   1. Fault injection tests + observability polish.

## 12. Acceptance Criteria
1. Any exec approval event can be routed through latch passkey flow and resolved back to OpenClaw.
2. Works in both deployment modes:
   1. Docker sidecar
   2. local daemon
3. Service survives restarts and transient outages without unsafe auto-allow.
4. Setup is executable by non-technical users via one guided wizard path.
5. Audit trail links OpenClaw approval id with Latch approval id and session context.

## 13. Open Questions
1. Default unresolved behavior at timeout:
   1. explicit deny vs leave pending for human fallback.
2. Preferred persistence for dedupe/replay:
   1. sqlite vs append-only jsonl.
3. Whether to ship chat message push from approver directly or keep it solely in latch.
