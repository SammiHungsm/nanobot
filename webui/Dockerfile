# syntax=docker/dockerfile:1
# Nanobot Web UI - FastAPI Frontend (Refactored v3.0)
# 🚀 Optimized for fast rebuilds with BuildKit cache
# 🌟 CPU-only PyTorch for local embedding (no NVIDIA dependencies)

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (rarely changes, good for caching)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# 🚀 Step 1: Copy requirements FIRST for better caching
COPY webui/requirements.txt ./requirements.txt

# 🌟 Step 2: Install CPU-only PyTorch FIRST (避免 GPU 巨大下載)
# sentence-transformers 依賴 torch，必須先安裝 CPU 版本
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1+cpu

# 🚀 Step 3: Install Python dependencies (sentence-transformers 會用已安裝的 CPU torch)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# 🚀 Step 4: Copy nanobot package (changes less frequently than webui code)
COPY nanobot/ /tmp/nanobot/
COPY pyproject.toml /tmp/nanobot/
COPY README.md /tmp/nanobot/
COPY bridge/ /tmp/nanobot/bridge/

# Install nanobot package with cache
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /tmp/nanobot/

# 🚀 Step 5: Copy application code LAST (changes frequently)
COPY webui/app/ ./app/
COPY webui/static/ ./static/

# Create data directories
RUN mkdir -p /data/pdfs /app/uploads /app/outputs

# 🌟 Copy entrypoint script (starts Hybrid server + WebUI)
COPY webui/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Create non-root user
RUN useradd --create-home --shell /bin/bash nanobot \
    && chown -R nanobot:nanobot /app /data

USER nanobot

EXPOSE 8080

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV MCP_SERVER_URL=http://OpenDataLoader-mcp:3000
ENV PDF_DATA_DIR=/data/pdfs
ENV PDF_UPLOAD_DIR=/app/uploads
ENV PDF_OUTPUT_DIR=/app/outputs
ENV USE_CUDA=false
ENV TORCH_DEVICE=cpu

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 🌟 Use entrypoint to start Hybrid server + WebUI
ENTRYPOINT ["./entrypoint.sh"]
