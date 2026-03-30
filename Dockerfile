# Nanobot Docker Image with LiteParse Integration
# Multi-stage build for minimal production image

FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install LiteParse global dependencies
RUN npm install -g @llamaindex/liteparse && \
    pip install --no-cache-dir pymupdf pillow

FROM base AS dependencies

# Copy requirements, README, and source code needed for hatchling build
COPY pyproject.toml README.md ./
COPY nanobot/ ./nanobot/
COPY bridge/ ./bridge/

ARG USE_CUDA=false

RUN if [ "$USE_CUDA" = "false" ] ; then \
      echo "Installing CPU-only PyTorch for faster build..." && \
      pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu ; \
    else \
      echo "Installing default (GPU-enabled) PyTorch..." ; \
    fi

# Install nanobot
RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir fastapi uvicorn

FROM base AS production

# Copy Python from dependencies
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
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

USER nanobot

# Data volume
VOLUME /app/.data

# Expose web interface port
EXPOSE 8080

# Set environment
ENV NANOBOT_CONFIG=/app/config/config.yaml
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run nanobot
CMD ["nanobot", "start", "--config", "/app/config/config.yaml"]