# 1. Native OpenClaw Tool Gating Via Latch API (Unified With MCP 2FA)

## Summary
Add a native-tool gating API to latch so OpenClaw first-party tools can use the same policy + approval + passkey flow already used for MCP tools.

## Reasoning
1. OpenClaw native tools currently bypass MCP proxy gating.
2. Users should keep OpenClaw first-party capabilities out of the box.
3. We should not duplicate policy or 2FA logic across MCP and native paths.
4. A single gate lifecycle reduces security drift and maintenance burden.

## Scope
1. Add native authorize/status endpoints in latch.
2. Reuse existing approval UI + WebAuthn decision endpoints.
3. Keep MCP behavior unchanged by routing both paths through shared gate logic.

## API Contract (Minimal)
1. `POST /v1/gate/native`
Input:
- `tool`
- `args`
- `sessionKey`
- `channel`
- `to`
- `agentId`

Output:
- `allow`
- `deny`
- `pending` with `approvalId`, `approvalUrl`

2. `GET /v1/gate/native/{approvalId}`
Output:
- `pending`
- `allow`
- `deny`

## OpenClaw Hook Behavior
1. Before native tool execution, call `POST /v1/gate/native`.
2. If `allow`, execute tool.
3. If `deny`, skip execution and post denial message.
4. If `pending`, show approval URL and poll `GET /v1/gate/native/{approvalId}` until terminal decision.

## Unified Model (Do Not Diverge)
Use one shared internal gate lifecycle for MCP + native:
1. `authorize(request) -> allow | deny | pending`
2. `resolve(approvalId) -> pending | allow | deny`
3. `notify(result)` (optional transport-specific output)

Adapters only:
1. MCP adapter (existing)
2. Native HTTP adapter (new)

## Key Code Locations
1. Policy core:
- `py/src/latch/policy.py` (`load_policy`, `evaluate`)

2. MCP gating path:
- `py/src/latch/serve.py` (`_add`, policy decision + approval URL response)

3. Approval + 2FA flow:
- `py/src/latch/approval.py` (`ApprovalServer`, `create_request`, `_post_decide`, `wait_for_decision`)

4. Chat feedback/webhook path:
- `py/src/latch/approval.py` (`_push_to_openclaw`)

## Implementation Steps
1. Extract shared gate decision service from current MCP path.
2. Add native HTTP endpoints using that service.
3. Add approval decision lookup/store by `approvalId` for polling.
4. Keep one audit schema across MCP and native requests.
5. Add tests for parity and regressions.

## Acceptance Criteria
1. Native OpenClaw tools can be `allow`/`deny`/`pending` gated via latch API.
2. Pending native calls use existing `/approval/{id}` and passkey verification.
3. MCP flow remains backward compatible.
4. Policy logic, approval sessions, and audit format are shared across MCP + native.

# 2. Onboarding UX Overhaul: README + Wizard-First Setup Flow

## Summary
Consolidate setup guidance across repo root and `py/` docs into one clear onboarding story, centered on a guided CLI/TUI wizard for first-time users.

## Current Pain Points (Observed)
1. Setup paths are fragmented across multiple sections (Hook mode, MCP mode, OpenClaw sidecar, plugin mode) with no primary decision flow.
2. The order of operations is unclear (install vs `latch init` vs `latch serve` vs passkey enrollment).
3. Root `README.md` and `py/README.md` partially duplicate content but diverge in detail.
4. “Quick Start” does not explicitly map “I am using X (OpenClaw/Claude/Codex)” to one canonical path.
5. The existing CLI has commands, but no first-run guided setup experience that verifies prerequisites and writes working config end-to-end.

## Goal
Make first success fast and obvious:
1. User picks platform/use case.
2. Wizard performs setup and outputs next command + verification step.
3. Docs mirror the wizard’s exact flow and become reference material rather than competing setup paths.

## Deliverables
1. Single canonical onboarding flow in docs:
   1. “Choose your path” matrix (OpenClaw sidecar, OpenClaw plugin, Claude hook, Codex hook).
   2. Path-specific copy-paste blocks with strict command order.
   3. A final “verify it works” step for each path.
2. CLI/TUI setup wizard:
   1. New command, e.g. `latch setup` (or `latch init --wizard`).
   2. Prompts for environment/platform.
   3. Writes/updates config files safely.
   4. Optionally tests connectivity and approval URL generation.
3. Doc parity:
   1. Root and `py/` READMEs share one source of truth and avoid duplicated drifting setup instructions.
   2. “Advanced/Manual setup” moved below “Wizard setup”.
4. Troubleshooting section:
   1. Cloudflare quick tunnel failures (EOF / invalid URL fallback).
   2. Docker env propagation gotchas.
   3. Path issues after install (`latch` not found).

## Proposed Wizard Flow
1. Detect environment and prerequisites:
   1. `pipx`/`uv`, Docker availability, OpenClaw presence.
2. Ask “What are you integrating with?”
   1. OpenClaw (Docker sidecar)
   2. OpenClaw (plugin/local)
   3. Claude Code hook
   4. Codex hook
3. Generate/update required files:
   1. `~/.agent-2fa/policy.yaml`
   2. `~/.agent-2fa/servers.yaml` (for MCP mode)
   3. Optional OpenClaw/mcporter config guidance
4. Offer enrollment:
   1. `latch enroll` or `latch enroll --remote`
5. Run verification checks:
   1. `latch status`
   2. Optional “send test approval” dry run
6. Print exact next steps and rollback instructions.

## Key Files To Update
1. Docs:
   1. `README.md` (primary onboarding and decision tree)
   2. `py/README.md` (package-focused but aligned flow)
2. CLI/Wizard:
   1. `py/src/latch/cli.py` (new setup command)
   2. `py/src/latch/init.py` (idempotent config creation helpers)
   3. `scripts/install-latch.sh` (post-install handoff to wizard)
3. Optional helper scripts:
   1. `scripts/setup-openclaw-mcporter.sh` (called from wizard when relevant)

## Acceptance Criteria
1. New user can complete setup for one platform without reading multiple sections.
2. Wizard can produce a working baseline configuration in <5 minutes.
3. Root and `py/` README setup instructions are consistent and non-contradictory.
4. Each integration path ends with a deterministic verification command.
