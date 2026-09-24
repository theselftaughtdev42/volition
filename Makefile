.PHONY: install dev start test lint format docker.build docker.run docker.latest

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

docker.build:
	docker build -t volition:local .

docker.run:
	docker run --rm --name volition -p 127.0.0.1:3000:3000 -v "${PWD}/config:/config:ro" -v "${PWD}/data:/data" volition:local

docker.latest:
	docker run --rm --name volition --platform linux/amd64 -p 127.0.0.1:3000:3000 -v "${PWD}/config:/config:ro" -v "${PWD}/data:/data" ghcr.io/theselftaughtdev42/volition:latest
