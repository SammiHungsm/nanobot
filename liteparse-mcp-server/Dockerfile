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
RUN npm install --omit=dev

FROM node-base AS production

# Copy Python base tools
COPY --from=python-base /usr/local/bin/python /usr/local/bin/python
COPY --from=python-base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy dependencies
COPY --from=dependencies /app/node_modules ./node_modules

# Copy server code
COPY index.js ./
COPY liteparse_data_cleaner.py ./

# Create data directory for PDFs and set ownership (must be before USER change)
RUN mkdir -p /data/pdfs

# Create non-root user for security
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001 && \
    chown nodejs:nodejs /data/pdfs

USER nodejs

# Expose port for HTTP transport
EXPOSE 3000

# Set working directory
WORKDIR /app

# Set environment for HTTP mode
ENV MODE=http
ENV PORT=3000

# Default command runs MCP server on HTTP
CMD ["node", "index.js"]
