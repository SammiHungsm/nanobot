#!/bin/bash
# Entrypoint for nanobot-webui with OpenDataLoader Hybrid Server
# This script starts both services:

echo "============================================================"
echo "🚀 Starting Nanobot WebUI with OpenDataLoader Hybrid Server"
echo "============================================================"

# 1. Start OpenDataLoader Hybrid Server in background
echo "🔥 Starting OpenDataLoader Hybrid Server..."
nohup opendataloader-pdf-hybrid \
    --port 5002 \
    --device cpu \
    --log-level info \
    > /tmp/hybrid.log 2>&1 &

HYBRID_PID=$!
echo "   Hybrid PID: $HYBRID_PID"

# 2. Wait for Hybrid server to be ready
echo "⏳ Waiting for Hybrid server..."
MAX_WAIT=30
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s http://localhost:5002/health > /dev/null 2>&1; then
        echo "   ✅ Hybrid server ready!"
        break
    fi
    sleep 1
    WAITED=$((WAITED + 1))
    echo "   Waiting... ($WAITED/$MAX_WAIT)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "   ⚠️ Hybrid server not responding, continuing anyway..."
    echo "   Log: $(tail -5 /tmp/hybrid.log)"
fi

# 3. Start WebUI
echo "============================================================"
echo "🌐 Starting WebUI Application..."
echo "============================================================"

# Execute the original command
exec python -m app.main