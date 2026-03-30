# Vanna AI Service
# Text-to-SQL with RAG training for financial queries

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    vanna[postgres] \
    psycopg2-binary \
    pandas

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import vanna; print('Vanna OK')" || exit 1

CMD ["python", "-c", "print('Vanna service ready')"]
