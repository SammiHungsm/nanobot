# PostgreSQL with Apache AGE and pgvector
FROM postgres:16

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libreadline-dev \
    zlib1g-dev \
    flex \
    bison \
    git \
    postgresql-server-dev-16 \
    && rm -rf /var/lib/apt/lists/*

# Build and install Apache AGE
RUN git clone --depth 1 --branch PG16/v1.5.0-rc0 https://github.com/apache/age.git /tmp/age \
    && cd /tmp/age \
    && make PG_CONFIG=/usr/bin/pg_config \
    && make PG_CONFIG=/usr/bin/pg_config install \
    && rm -rf /tmp/age

# Build and install pgvector
RUN git clone https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && git checkout v0.7.4 \
    && make PG_CONFIG=/usr/bin/pg_config \
    && make PG_CONFIG=/usr/bin/pg_config install \
    && rm -rf /tmp/pgvector

# Copy initialization script
COPY init-age.sql /docker-entrypoint-initdb.d/01-init-age.sql
