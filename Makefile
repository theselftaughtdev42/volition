.PHONY: install dev start test coverage test.docker lint format typecheck lock.check zizmor check \
	release release.check docker.build docker.run docker.latest

# Every check is defined here once: the git hooks (.pre-commit-config.yaml) and CI (.github/workflows/ci.yml)
# call these targets or the same `uv run` commands, and every tool is pinned in uv.lock.

install:
	uv sync
	uv run pre-commit install

dev:
	uv run fastapi dev --port 3000

start:
	uv run python -m volition

test:
	uv run pytest

# Branch coverage of volition/, gated at 100% (fail_under in pyproject.toml).
coverage:
	uv run pytest --cov

# The suite inside the dev image, against production's Pango. The source is mounted, not baked in.
test.docker:
	docker build --target dev -t volition:dev .
	docker run --rm -v "$(CURDIR):/app" volition:dev make coverage

lint:
	uv run ruff check volition tests
	uv run ruff format --check volition tests

format:
	uv run ruff check --fix volition tests
	uv run ruff format volition tests

typecheck:
	uv run ty check --error-on-warning

lock.check:
	uv lock --check

zizmor:
	uv run zizmor .github

check: lint typecheck lock.check zizmor coverage

# Cut a release: `make release BUMP=patch|minor|major` or `make release V=1.2.3`.
# Bumps pyproject.toml and uv.lock, commits, tags vX.Y.Z and (after a prompt) pushes both;
# the tag push triggers .github/workflows/publish.yml.
release: release.check lint test
	@set -e; \
	if [ -n "$(V)" ]; then uv version --no-sync "$(V)"; else uv version --no-sync --bump "$(BUMP)"; fi; \
	version=$$(uv version --short); \
	if git rev-parse -q --verify "refs/tags/v$$version" >/dev/null; then \
		git checkout -- pyproject.toml uv.lock; \
		echo "tag v$$version already exists"; exit 1; \
	fi; \
	SKIP=no-commit-to-main git commit -q -m "release v$$version" pyproject.toml uv.lock; \
	git tag -a "v$$version" -m "v$$version"; \
	printf "Push main and v$$version to origin? [y/N] "; read answer; \
	if [ "$$answer" = y ]; then \
		git push --atomic origin main "v$$version"; \
	else \
		echo "Not pushed. To push: git push --atomic origin main v$$version"; \
		echo "To undo:  git tag -d v$$version && git reset --hard HEAD~1"; \
	fi

release.check:
	@set -e; \
	if [ -n "$(V)" ] && [ -n "$(BUMP)" ]; then echo "set V or BUMP, not both"; exit 1; fi; \
	if [ -z "$(V)$(BUMP)" ]; then echo "usage: make release BUMP=patch|minor|major  or  make release V=1.2.3"; exit 1; fi; \
	if [ "$$(git branch --show-current)" != main ]; then echo "releases are cut from main"; exit 1; fi; \
	if [ -n "$$(git status --porcelain)" ]; then echo "working tree is not clean"; exit 1; fi; \
	git fetch -q --tags origin main; \
	if [ "$$(git rev-parse HEAD)" != "$$(git rev-parse origin/main)" ]; then echo "main is not in sync with origin/main"; exit 1; fi

docker.build:
	docker build -t volition:local .

docker.run:
	docker run --rm --name volition -p 127.0.0.1:3000:3000 -v "${PWD}/data:/data" volition:local

docker.latest:
	docker run --rm --name volition --platform linux/amd64 -p 127.0.0.1:3000:3000 -v "${PWD}/data:/data" ghcr.io/theselftaughtdev42/volition:latest
