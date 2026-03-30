# Nanobot Docker Image
# Lightweight production image without heavy ML dependencies

FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

FROM base AS dependencies

# Copy requirements, README, and source code needed for hatchling build
COPY pyproject.toml README.md ./
COPY nanobot/ ./nanobot/
COPY bridge/ ./bridge/

# Install nanobot and dependencies (no PyTorch by default)
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