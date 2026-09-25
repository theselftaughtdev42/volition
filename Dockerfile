# syntax=docker/dockerfile:1

# --- Build: resolve the venv with uv, which itself doesn't ship. ---
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS build

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# --- Runtime: plain Python plus the Pango stack WeasyPrint lays text out with. ---
FROM python:3.14-slim-bookworm

# No font packages: the invoice inlines its own fonts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY . .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=3000 \
    CONFIG_DIR=/config \
    DATA_DIR=/data

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:3000/health', timeout=4).status == 200 else 1)"]

CMD ["python", "-m", "volition"]
