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
# 1. 鎖定 vanna 0.7.x 版本（使用經典的 chromadb 架構）
# 2. 限制 numpy<2.0.0 避免 ChromaDB 崩潰
# 3. vanna[chromadb,postgres] 已經包含 chromadb 和 psycopg2，但需要額外安裝 openai
# 4. vanna[openai] 包含 openai 依賴
RUN pip install --no-cache-dir \
    "vanna[chromadb,postgres,openai]>=0.7.0,<1.0.0" \
    "numpy<2.0.0" \
    pandas \
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
