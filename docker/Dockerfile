# syntax=docker/dockerfile:1.7

# ---- Build stage: resolve dependencies and build the wheel -----------------
FROM python:3.15-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN pip install --no-cache-dir uv==0.11.3

WORKDIR /build

COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# ---- Runtime stage: minimal image, unprivileged user ------------------------
FROM python:3.15-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="PulseWatch" \
      org.opencontainers.image.description="Linux-first system monitoring API" \
      org.opencontainers.image.source="https://github.com/sirsona/pulsewatch" \
      org.opencontainers.image.licenses="MIT"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PULSEWATCH_HOST=0.0.0.0 \
    PULSEWATCH_PORT=8000 \
    PULSEWATCH_ENVIRONMENT=production \
    PULSEWATCH_LOG_FORMAT=json

RUN groupadd --system --gid 10001 pulsewatch \
    && useradd --system --uid 10001 --gid pulsewatch \
       --home-dir /app --shell /usr/sbin/nologin pulsewatch

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).read()"]

STOPSIGNAL SIGINT

CMD ["pulsewatch"]
