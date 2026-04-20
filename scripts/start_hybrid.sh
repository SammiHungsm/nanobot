#!/bin/bash
# Start OpenDataLoader Hybrid Server
# Usage: docker exec nanobot-webui bash /app/scripts/start_hybrid.sh

echo "Starting OpenDataLoader Hybrid Server..."

# Check if already running
if curl -s http://localhost:5002/health > /dev/null 2>&1; then
    echo "✅ Hybrid server already running"
    exit 0
fi

# Start server in background
nohup opendataloader-pdf-hybrid --port 5002 --device cpu --log-level info > /tmp/hybrid.log 2>&1 &

echo "Waiting for server to start..."
sleep 10

# Check if started
if curl -s http://localhost:5002/health; then
    echo ""
    echo "✅ Hybrid server started successfully"
    echo "   URL: http://localhost:5002"
    echo "   Device: CPU"
    echo "   Log: /tmp/hybrid.log"
else
    echo "❌ Failed to start Hybrid server"
    cat /tmp/hybrid.log
    exit 1
fi