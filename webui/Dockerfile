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
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy nanobot package from parent directory and install it
COPY ../nanobot/ /tmp/nanobot/
COPY ../pyproject.toml /tmp/nanobot/
COPY ../README.md /tmp/nanobot/
COPY ../bridge/ /tmp/nanobot/bridge/
RUN pip install --no-cache-dir /tmp/nanobot/

# Copy application code (new modular structure)
COPY app/ ./app/

# Copy static files (HTML, CSS, JS)
COPY static/ ./static/

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
ENV USE_CUDA=false
ENV TORCH_DEVICE=cpu

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["python", "-m", "app.main"]
