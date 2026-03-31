# Nanobot Web UI - FastAPI Frontend
# Lightweight container for serving the financial chat interface
# CPU-optimized (no GPU dependencies needed for web UI)

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
COPY requirements.txt .

# Install Python dependencies (CPU-only, no heavy ML)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY chat_logic.py .

# Copy static files (HTML, CSS, JS)
COPY static/ ./static/

# Create data directory for PDFs (mounted at runtime)
RUN mkdir -p /data/pdfs

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash nanobot \
    && chown -R nanobot:nanobot /app /data

USER nanobot

# Expose port
EXPOSE 8080

# Set environment variables (CPU mode by default)
ENV PYTHONUNBUFFERED=1
ENV MCP_SERVER_URL=http://liteparse-mcp:3000
ENV PDF_DATA_DIR=/data/pdfs
ENV USE_CUDA=false
ENV TORCH_DEVICE=cpu

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["python", "main.py"]
