# Vanna AI Service
# Text-to-SQL with RAG training for financial queries

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    vanna[chromadb,postgres] \
    psycopg2-binary \
    pandas \
    chromadb \
    loguru

# Create data directory for ChromaDB persistence
RUN mkdir -p /app/data

# Copy startup script
COPY start.py /app/start.py

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from vanna.chromadb import ChromaDB_VectorStore; print('Vanna OK')" || exit 1

# Run startup script (trains Vanna and keeps service running)
CMD ["python", "/app/start.py"]
