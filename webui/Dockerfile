# Nanobot Web UI - FastAPI Frontend (Refactored v2.0)
# Modular architecture with separated API routes, services, and schemas

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY webui/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy nanobot package
COPY nanobot/ /tmp/nanobot/
COPY pyproject.toml /tmp/nanobot/
COPY README.md /tmp/nanobot/
COPY bridge/ /tmp/nanobot/bridge/

# 🚀 關鍵修復：先強制安裝 CPU 版本的 PyTorch，避免 pip 自動下載 NVIDIA 版本
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu torch torchvision

# 然後再安裝 nanobot (此時 pip 發現 torch 已經裝了，就會跳過下載 NVIDIA 套件)
RUN pip install --no-cache-dir /tmp/nanobot/

# Copy application code (需加上 webui/ 前綴)
COPY webui/app/ ./app/

# Copy static files (HTML, CSS, JS)
COPY webui/static/ ./static/

# Create data directories for PDFs
RUN mkdir -p /data/pdfs /app/uploads /app/outputs

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash nanobot \
    && chown -R nanobot:nanobot /app /data

USER nanobot

# Expose port
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV MCP_SERVER_URL=http://liteparse-mcp:3000
ENV PDF_DATA_DIR=/data/pdfs
ENV PDF_UPLOAD_DIR=/app/uploads
ENV PDF_OUTPUT_DIR=/app/outputs
# Force CPU-only mode (no CUDA)
ENV USE_CUDA=false
ENV TORCH_DEVICE=cpu

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["python", "-m", "app.main"]
