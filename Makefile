.PHONY: build test run-hook-ts run-hook-py run-serve-py

build:
	cd ts && npm run build

test:
	cd ts && npm test
	cd py && uv run pytest

run-hook-ts:
	cd ts && npm run hook

run-hook-py:
	cd py && uv run latch-hook

run-serve-py:
	cd py && uv run latch-serve
