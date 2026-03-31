# Vanna AI Service
# Text-to-SQL with RAG training for financial queries
# Supports continuous learning (邊做邊學) via REST API

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
RUN pip install --no-cache-dir \
    vanna[chromadb,postgres] \
    psycopg2-binary \
    pandas \
    chromadb \
    loguru \
    fastapi \
    uvicorn

# Create data directory for ChromaDB persistence
RUN mkdir -p /app/data /app/data/raw /app/data/chromadb

# Copy startup script
COPY start.py /app/start.py

# Expose API port
EXPOSE 8082

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1

# Run FastAPI server with uvicorn
CMD ["python", "/app/start.py"]
