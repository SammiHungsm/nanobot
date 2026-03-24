# Nanobot Web UI - FastAPI Frontend
# Lightweight container for serving the financial chat interface

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY chat_logic.py .
COPY ui.html .

# Create data directory for PDFs (mounted at runtime)
RUN mkdir -p /data/pdfs

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash nanobot \
    && chown -R nanobot:nanobot /app /data

USER nanobot

# Expose port
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV MCP_SERVER_URL=http://liteparse-mcp:3000
ENV PDF_DATA_DIR=/data/pdfs

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["python", "main.py"]
