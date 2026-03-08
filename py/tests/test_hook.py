import asyncio
import json
import importlib
from latch.policy import evaluate, load_policy
from latch.audit import append, read


def test_evaluate_allow():
    policy = {"defaultAction": "allow", "rules": []}
    action, reason = evaluate("Read", policy)
    assert action == "allow"


def test_evaluate_rule_match():
    policy = {"defaultAction": "allow", "rules": [{"match": {"tool": "Bash"}, "action": "ask"}]}
    action, _ = evaluate("Bash", policy)
    assert action == "ask"


def test_evaluate_regex():
    policy = {"defaultAction": "allow", "rules": [{"match": {"tool": "Edit|Write"}, "action": "deny"}]}
    assert evaluate("Edit", policy)[0] == "deny"
    assert evaluate("Write", policy)[0] == "deny"
    assert evaluate("Read", policy)[0] == "allow"


def test_hook_fail_closed_on_exception(monkeypatch, capsys):
    hook = importlib.import_module("latch.hook")

    def raise_policy_error():
        raise RuntimeError("boom")

    audit_calls = []
    monkeypatch.setattr(hook, "load_policy", raise_policy_error)
    monkeypatch.setattr(hook, "append", lambda *args, **kwargs: audit_calls.append((args, kwargs)))

    payload = {"tool_name": "Bash", "tool_input": {"cmd": "whoami"}}
    asyncio.run(hook._main(json.dumps(payload)))
    output = json.loads(capsys.readouterr().out)

    hook_output = output["hookSpecificOutput"]
    assert hook_output["permissionDecision"] == "deny"
    assert "fail-closed" in hook_output["permissionDecisionReason"]
    assert len(audit_calls) == 1
    assert audit_calls[0][0][2] == "deny"
    assert audit_calls[0][0][3] == "deny"
