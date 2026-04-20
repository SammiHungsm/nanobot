#!/bin/bash
# Entrypoint for nanobot-webui (LlamaParse-only architecture)
# OpenDataLoader Hybrid has been removed - using LlamaParse Cloud API

echo "============================================================"
echo "🚀 Starting Nanobot WebUI (LlamaParse Architecture)"
echo "============================================================"

# No longer need Hybrid Server - using LlamaParse Cloud API
echo "✅ Using LlamaParse Cloud API for PDF parsing"
echo "   Configure LLAMA_CLOUD_API_KEY in environment"

# Start WebUI directly
echo "============================================================"
echo "🌐 Starting WebUI Application..."
echo "============================================================"

# Execute the original command
exec python -m app.main