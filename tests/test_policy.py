import pytest
from latch import policy


@pytest.fixture
def default_policy():
    return {
        "defaultAction": "approve",
        "rules": [
            {"match": {"tool": "(ls|pwd|whoami|cat|head|tail|echo|date|env)"}, "action": "allow"},
            {"match": {"tool": "(rm|chmod|chown|kill|shutdown|reboot)"}, "action": "deny"},
        ],
    }


def test_allow_match(default_policy):
    action, _ = policy.evaluate("ls", default_policy)
    assert action == "allow"
    action, _ = policy.evaluate("cat", default_policy)
    assert action == "allow"


def test_deny_match(default_policy):
    action, _ = policy.evaluate("rm", default_policy)
    assert action == "deny"
    action, _ = policy.evaluate("kill", default_policy)
    assert action == "deny"


def test_default_action(default_policy):
    action, _ = policy.evaluate("unknown_command", default_policy)
    assert action == "approve"


def test_deny_default():
    pol = {"defaultAction": "deny", "rules": []}
    action, _ = policy.evaluate("Anything", pol)
    assert action == "deny"


def test_first_rule_wins():
    pol = {
        "defaultAction": "allow",
        "rules": [
            {"match": {"tool": "Bash"}, "action": "deny"},
            {"match": {"tool": "Bash"}, "action": "approve"},
        ],
    }
    action, _ = policy.evaluate("Bash", pol)
    assert action == "deny"
