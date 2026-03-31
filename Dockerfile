# Nanobot Docker Image - CPU Only Version
# Optimized for CPU with lightweight PyTorch installation

FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

FROM base AS dependencies

# Copy requirements, README, and source code needed for hatchling build
COPY pyproject.toml README.md ./
COPY nanobot/ ./nanobot/
COPY bridge/ ./bridge/

# Install nanobot core dependencies WITHOUT opendataloader-pdf (has CUDA deps)
# Use --no-deps to skip opendataloader-pdf, then install it separately with CPU extra
RUN pip install --no-cache-dir typer anthropic pydantic pydantic-settings \
    websockets websocket-client httpx ddgs oauth-cli-kit loguru \
    readability-lxml rich croniter dingtalk-stream python-telegram-bot \
    lark-oapi socksio python-socketio msgpack slack-sdk slackify-markdown \
    qq-botpy python-socks prompt-toolkit questionary mcp json-repair \
    chardet openai tiktoken psycopg2-binary vanna[postgres] aiohttp \
    fastapi uvicorn asyncpg

# Install CPU-only PyTorch FIRST (before opendataloader)
# Removed torchaudio - not needed for PDF processing (saves ~50MB and build time)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1 \
    torchvision==0.20.1

# Install opendataloader-pdf with CPU-only dependencies (no CUDA)
RUN pip install --no-cache-dir opendataloader-pdf[cpu]>=2.2.0

# Install nanobot package itself (creates console script)
RUN pip install --no-cache-dir .

FROM base AS production

# Copy Python packages from dependencies
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy nanobot console script from dependencies
COPY --from=dependencies /usr/local/bin/nanobot /usr/local/bin/nanobot

# Copy application code
COPY nanobot/ ./nanobot/
COPY bridge/ ./bridge/

# Create config directory (will be mounted at runtime)
RUN mkdir -p /app/config

# Create non-root user and setup directories
RUN useradd --create-home --shell /bin/bash nanobot \
    && mkdir -p /app/.data /app/config \
    && chown -R nanobot:nanobot /app

ENV PATH="/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

USER nanobot

# Data volume
VOLUME /app/.data

# Expose web interface port
EXPOSE 8080

# Set environment variables for CPU mode
ENV NANOBOT_CONFIG=/app/config/config.yaml
ENV PYTHONUNBUFFERED=1
ENV USE_CUDA=false
ENV TORCH_DEVICE=cpu

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run nanobot
CMD ["nanobot", "start", "--config", "/app/config/config.yaml"]
