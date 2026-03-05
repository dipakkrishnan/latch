import json
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
