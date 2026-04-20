#!/bin/bash
# Entrypoint for nanobot-webui with OpenDataLoader Hybrid Server (GPU Version)
# Includes CUDA cache clearing mechanism

echo "============================================================"
echo "🚀 Starting Nanobot WebUI with OpenDataLoader Hybrid Server (GPU)"
echo "============================================================"

# 1. Start OpenDataLoader Hybrid Server with CUDA
echo "🔥 Starting OpenDataLoader Hybrid Server (CUDA)..."
nohup opendataloader-pdf-hybrid \
    --port 5002 \
    --device cuda \
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

# 3. Start CUDA Cache Cleaner (background)
echo "🧹 Starting CUDA Cache Cleaner..."
nohup python -c "
import time
import requests
import subprocess

print('Cache cleaner started')

while True:
    time.sleep(60)  # 每 60 秒检查一次
    
    # 检查显存使用情况
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], 
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            mem_used = int(result.stdout.strip())
            print(f'GPU Memory: {mem_used} MiB')
            
            # 如果显存超过 6GB，触发清理
            if mem_used > 6000:
                print('High GPU memory usage, triggering cleanup...')
                # 发送信号让 Docling 重置
                try:
                    requests.post('http://localhost:5002/v1/reset', timeout=10)
                except:
                    pass
    except Exception as e:
        print(f'Error checking memory: {e}')
" > /tmp/cache_cleaner.log 2>&1 &

CLEANER_PID=$!
echo "   Cache Cleaner PID: $CLEANER_PID"

# 4. Start WebUI
echo "============================================================"
echo "🌐 Starting WebUI Application..."
echo "============================================================"

# Execute the original command
exec python -m app.main