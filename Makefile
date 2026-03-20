.PHONY: test hook serve dashboard approver approver-check

test:
	cd py && uv run pytest

hook:
	cd py && uv run latch-hook

serve:
	cd py && uv run latch-serve

dashboard:
	cd py && uv run latch-dashboard

approver:
	uv run --project py python -m core.clawdian_approver.main run

approver-check:
	uv run --project py python -m core.clawdian_approver.main check
