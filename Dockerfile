# syntax=docker/dockerfile:1
# Nanobot Docker Image - CPU Only Version
# 🚀 Optimized for fast rebuilds with BuildKit cache and multi-stage build

FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies (rarely changes)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# ===========================================
# Stage 1: Dependencies (cached layer)
# ===========================================
FROM base AS dependencies

# Copy ONLY dependency files first (for better caching)
COPY pyproject.toml README.md ./
COPY nanobot/ ./nanobot/
COPY bridge/ ./bridge/

# 🚀 Install with BuildKit cache - pip packages cached locally
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install typer anthropic pydantic pydantic-settings \
    websockets websocket-client httpx ddgs oauth-cli-kit loguru \
    readability-lxml rich croniter dingtalk-stream python-telegram-bot \
    lark-oapi socksio python-socketio msgpack slack-sdk slackify-markdown \
    qq-botpy python-socks prompt-toolkit questionary mcp json-repair \
    chardet openai tiktoken psycopg2-binary vanna[postgres] aiohttp \
    fastapi uvicorn asyncpg

# 🚀 Install CPU-only PyTorch with cache (2-3GB, this is the slow part)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1 \
    torchvision==0.20.1

# Install opendataloader-pdf with CPU-only dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install opendataloader-pdf[cpu]>=2.2.0

# Install nanobot package itself
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install .

# ===========================================
# Stage 2: Production (minimal image)
# ===========================================
FROM base AS production

# Copy Python packages from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy nanobot console script
COPY --from=dependencies /usr/local/bin/nanobot /usr/local/bin/nanobot

# 🚀 Copy application code LAST (changes frequently)
COPY nanobot/ ./nanobot/
COPY bridge/ ./bridge/

# Create config directory
RUN mkdir -p /app/config

# Create non-root user
RUN useradd --create-home --shell /bin/bash nanobot \
    && mkdir -p /app/.data /app/config \
    && chown -R nanobot:nanobot /app

ENV PATH="/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

USER nanobot

VOLUME /app/.data

EXPOSE 8080

ENV NANOBOT_CONFIG=/app/config/config.json
ENV PYTHONUNBUFFERED=1
ENV USE_CUDA=false
ENV TORCH_DEVICE=cpu

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["nanobot", "gateway", "--config", "/app/config/config.json"]
