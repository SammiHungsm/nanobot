# syntax=docker/dockerfile:1
# Vanna AI Service - Text-to-SQL with RAG training
# 🚀 Optimized for fast rebuilds with BuildKit cache

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (rarely changes, good for caching)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 🚀 Step 1: Create requirements and install dependencies FIRST
# This layer will be cached as long as requirements don't change
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install \
    "vanna[chromadb,postgres,openai]>=0.7.0,<1.0.0" \
    "numpy<2.0.0" \
    pandas \
    loguru \
    fastapi \
    uvicorn

# Create data directory for ChromaDB persistence
RUN mkdir -p /app/data/raw /app/data/chromadb

# 🚀 Step 2: Copy application code LAST (changes frequently)
# This way, code changes don't invalidate the pip install cache
COPY start.py /app/start.py
COPY vanna_training.py /app/vanna_training.py

# Copy JSON training files
COPY data/ddl.json /app/data/ddl.json
COPY data/ddl_whitelist.json /app/data/ddl_whitelist.json
COPY data/documentation.json /app/data/documentation.json
COPY data/sql_pairs.json /app/data/sql_pairs.json

# Expose API port
EXPOSE 8082

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1

# Run FastAPI server with uvicorn
CMD ["python", "/app/start.py"]
