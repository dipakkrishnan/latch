import asyncio, json, os, subprocess, sys

from .policy import load_policy, evaluate
from .audit import append
from .approval import start_approval_flow


def _detect_client():
    explicit = os.environ.get("AGENT_2FA_CLIENT", "")
    if explicit:
        c = _normalize(explicit)
        if c != "unknown":
            return c
    env = os.environ
    if any(k in env for k in ("CODEX_THREAD_ID", "CODEX_SANDBOX", "CODEX_CI")):
        return "codex"
    keys = " ".join(env.keys()).lower()
    if "claude" in keys:
        return "claude-code"
    if "openclaw" in keys:
        return "openclaw"
    return _normalize(_ancestry(6))


def _normalize(s):
    s = s.lower()
    if "claude" in s:
        return "claude-code"
    if "codex" in s:
        return "codex"
    if "openclaw" in s:
        return "openclaw"
    return "unknown"


def _ancestry(depth):
    cmds, pid = [], os.getppid()
    for _ in range(depth):
        try:
            out = subprocess.check_output(["ps", "-o", "ppid=,command=", "-p", str(pid)], text=True).strip()
            if not out:
                break
            parts = out.split(None, 1)
            pid = int(parts[0])
            if len(parts) > 1:
                cmds.append(parts[1])
        except Exception:
            break
    return " ".join(cmds)


_CLIENT = _detect_client()
_AGENT_ID = os.environ.get("AGENT_2FA_AGENT_ID") or (f"{_CLIENT}-adhoc" if _CLIENT != "unknown" else "unknown")


def _to_decision(action):
    if action == "allow":
        return "allow"
    if action == "deny":
        return "deny"
    return "ask"


def _output(decision, reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}}), end="")


async def _main(raw):
    try:
        data = json.loads(raw)
        tool = data["tool_name"]
        tool_input = data.get("tool_input", {})
        policy = load_policy()
        action, reason = evaluate(tool, policy)

        if action in ("browser", "webauthn"):
            approved = await start_approval_flow(tool, tool_input, require_webauthn=(action == "webauthn"))
            decision = "allow" if approved else "deny"
            reason = f"{'Approved' if approved else 'Denied'} in browser ({action})"
            try:
                append(tool, tool_input, action, decision, reason, action, "hook")
            except Exception as e:
                print(f"Audit error (ignored): {e}", file=sys.stderr)
            _output(decision, reason)
            return

        decision = _to_decision(action)
        try:
            append(tool, tool_input, action, decision, reason, "policy", "hook")
        except Exception as e:
            print(f"Audit error (ignored): {e}", file=sys.stderr)
        _output(decision, reason)
    except Exception as e:
        print(f"Hook error: {e}", file=sys.stderr)
        try:
            append("unknown", {}, "allow", "allow", f"Hook error (fail-open): {e}", "fail-open", "hook")
        except Exception:
            pass
        _output("allow", f"Hook error (fail-open): {e}")


def main():
    raw = sys.stdin.read()
    asyncio.run(_main(raw))
