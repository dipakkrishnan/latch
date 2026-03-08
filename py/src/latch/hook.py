import asyncio, json, os, subprocess, sys

from .policy import load_policy, evaluate
from .audit import append
from .approval import start_approval_flow
from .logging_utils import env_flag, init_logger, debug_enabled


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
_DEBUG = debug_enabled(env_flag("LATCH_HOOK_DEBUG"))
_LOGGER = init_logger("latch.hook", debug=_DEBUG)


def _to_decision(action):
    if action == "allow":
        return "allow"
    if action == "deny":
        return "deny"
    return "ask"


def _output(decision, reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}}), end="")


def _log(message):
    if not _DEBUG:
        return
    _LOGGER.debug(message)


async def _main(raw):
    try:
        _log(f"hook invoked; client={_CLIENT} agent_id={_AGENT_ID}")
        data = json.loads(raw)
        tool = data["tool_name"]
        tool_input = data.get("tool_input", {})
        _log(f"parsed input; tool={tool}")
        policy = load_policy()
        action, reason = evaluate(tool, policy)
        _log(f"policy evaluated; action={action} reason={reason}")

        if action in ("browser", "webauthn"):
            _log(f"starting approval flow; mode={action}")
            approved, flow_reason = await start_approval_flow(
                tool,
                tool_input,
                require_webauthn=(action == "webauthn"),
            )
            decision = "allow" if approved else "deny"
            reason = flow_reason
            _log(f"approval flow complete; approved={approved} decision={decision}")
            try:
                append(tool, tool_input, action, decision, reason, action, "hook")
                _log("audit append success")
            except Exception as e:
                _LOGGER.warning("Audit error (ignored): %s", e)
                _log(f"audit append failed: {e}")
            _output(decision, reason)
            _log(f"response emitted; decision={decision}")
            return

        decision = _to_decision(action)
        try:
            append(tool, tool_input, action, decision, reason, "policy", "hook")
            _log("audit append success")
        except Exception as e:
            _LOGGER.warning("Audit error (ignored): %s", e)
            _log(f"audit append failed: {e}")
        _output(decision, reason)
        _log(f"response emitted; decision={decision}")
    except Exception as e:
        _LOGGER.error("Hook error: %s", e)
        _log(f"hook exception: {e}")
        try:
            append("unknown", {}, "deny", "deny", "Hook error (fail-closed)", "policy", "hook")
            _log("fail-closed audit append success")
        except Exception:
            _log("fail-closed audit append failed")
            pass
        _output("deny", "Hook error (fail-closed)")
        _log("response emitted; decision=deny (fail-closed)")


def main():
    raw = sys.stdin.read()
    asyncio.run(_main(raw))
