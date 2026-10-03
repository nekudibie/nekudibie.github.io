# Optional container image for the Python roles (api / vault / worker). Native systemd + uv is
# the default on real hosts (see deploy/systemd); this image exists for people who prefer Compose.
# Build:  docker build -f deploy/docker/Dockerfile -t companion:local .
# Run:    docker run --rm -p 8710:8710 -v $PWD/data:/app/data --env-file .env companion:local companion-api serve --host 0.0.0.0

FROM node:22-bookworm-slim AS ui
WORKDIR /ui
COPY apps/desk/package.json apps/desk/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/desk/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/
COPY apps/vault/pyproject.toml apps/vault/
COPY apps/worker/pyproject.toml apps/worker/
COPY apps/audio/pyproject.toml apps/audio/
COPY packages/core/pyproject.toml packages/core/
COPY packages/contracts/pyproject.toml packages/contracts/
COPY packages/integrations/pyproject.toml packages/integrations/
COPY packages/tutor/pyproject.toml packages/tutor/
COPY packages/robotics/pyproject.toml packages/robotics/
COPY apps packages ./
COPY config ./config
COPY --from=ui /ui/dist ./apps/desk/dist
RUN uv sync --all-packages --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" COMPANION_CONFIG=/app/config/local.yaml
RUN useradd -r -u 10001 companion && mkdir -p /app/data && chown -R companion /app/data
USER companion
EXPOSE 8710 8720
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8710/healthz', timeout=3).status==200 else 1)" || exit 1
CMD ["companion-api", "serve", "--host", "0.0.0.0"]
