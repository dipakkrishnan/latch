.PHONY: test run

test:
	uv run --with pytest --with pytest-aiohttp pytest

run:
	uv run latch run
