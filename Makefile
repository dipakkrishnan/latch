.PHONY: test hook serve dashboard

test:
	cd py && uv run pytest

hook:
	cd py && uv run latch-hook

serve:
	cd py && uv run latch-serve

dashboard:
	cd py && uv run latch-dashboard
