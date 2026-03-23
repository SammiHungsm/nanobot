# Nanobot Docker Image with LiteParse Integration
# Multi-stage build for minimal production image

FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

FROM base AS dependencies

# Copy requirements
COPY pyproject.toml .

# Install nanobot
RUN pip install --no-cache-dir -e .

FROM base AS production

# Copy Python from dependencies
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin/nanobot /usr/local/bin/nanobot

# Copy application code
COPY nanobot/ ./nanobot/
COPY bridge/ ./bridge/

# Create non-root user
RUN useradd --create-home --shell /bin/bash nanobot
USER nanobot

# Create data directory
RUN mkdir -p /app/.data
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
