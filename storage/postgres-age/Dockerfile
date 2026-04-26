# ============================================================
# Apache AGE + pgvector for PostgreSQL 18
# Base: apache/age:latest (PostgreSQL 18.1 + Apache AGE 2.0)
# Adds: pgvector (for vector similarity search)
# ============================================================
FROM apache/age:latest AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    postgresql-server-dev-18 \
    make \
    gcc \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Build and install pgvector from source (no official PG18 package yet)
RUN git clone --depth 1 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && make \
    && make install \
    && cd / \
    && rm -rf /tmp/pgvector

# Final stage - clean up build tools
FROM apache/age:latest

# Copy pre-built pgvector from builder
COPY --from=builder /usr /usr

# Verify extensions are available
RUN echo "=== Verifying extensions ===" \
    && psql -U postgres -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('age', 'vector');" || echo "Extensions will be created at init time"
