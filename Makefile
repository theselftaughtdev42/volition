.PHONY: install dev start test lint format

install:
	uv sync
	uv run playwright install chromium

dev:
	uv run fastapi dev --port 3000

start:
	uv run python -m volition

test:
	uv run pytest

lint:
	uvx ruff check volition tests
	uvx ruff format --check volition tests

format:
	uvx ruff check --fix volition tests
	uvx ruff format volition tests
