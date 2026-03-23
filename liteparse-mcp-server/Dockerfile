# LiteParse MCP Server - Docker Image
# Provides LiteParse CLI + MCP Server + Python Data Cleaner for financial reports

FROM python:3.11-slim AS python-base

# Install Python dependencies for data cleaner
RUN pip install --no-cache-dir pymupdf pillow

FROM node:20-alpine AS node-base

WORKDIR /app

# Install LiteParse CLI globally
RUN npm install -g @llamaindex/liteparse

# Verify installation
RUN lit --version

# Install Python (needed for data cleaner)
RUN apk add --no-cache python3 py3-pip

FROM node-base AS dependencies

# Copy package files
COPY package*.json ./

# Install MCP SDK and dependencies
RUN npm ci --only=production

FROM node-base AS production

# Copy Python base tools
COPY --from=python-base /usr/local/bin/python /usr/local/bin/python
COPY --from=python-base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy dependencies
COPY --from=dependencies /app/node_modules ./node_modules

# Copy server code
COPY index.js ./
COPY liteparse_data_cleaner.py ./

# Create non-root user for security
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

USER nodejs

# Create data directory for PDFs
RUN mkdir -p /data/pdfs && chown nodejs:nodejs /data/pdfs

# Expose port for SSE transport (if needed)
EXPOSE 3000

# Set working directory
WORKDIR /app

# Default command runs MCP server on stdio
CMD ["node", "index.js"]
