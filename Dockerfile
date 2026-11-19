# syntax=docker/dockerfile:1

# --- Build: resolve the venv with uv, which itself doesn't ship. ---
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS build

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# --- Dev build: the same, plus the dev group, in /opt/venv so a mounted source tree can't shadow it. ---
FROM build AS dev-build

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-install-project

# --- Base: plain Python plus the Pango stack WeasyPrint lays text out with. ---
FROM python:3.15-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9 AS base

# No font packages: the invoice inlines its own fonts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/*

# --- Dev: production's runtime with the dev tools, for `make test.docker` and CI. ---
# The source is mounted at /app; nothing is written back to it.
FROM base AS dev

RUN apt-get update \
    && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/uv /usr/local/bin/uv
COPY --from=dev-build /opt/venv /opt/venv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_NO_SYNC=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTEST_ADDOPTS="-p no:cacheprovider" \
    COVERAGE_FILE=/tmp/.coverage

CMD ["make", "coverage"]

# --- Runtime (the default target, and what ships). ---
FROM base

# A non-root user that owns only /data: the code and venv stay read-only to the app.
RUN useradd --system --uid 10001 --no-create-home volition \
    && mkdir /data && chown volition:volition /data

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY . .
# Compiled now, since the app can't write __pycache__ at runtime.
RUN python -m compileall -q volition

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    DATA_DIR=/data

USER volition
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status == 200 else 1)"]

CMD ["python", "-m", "volition"]
