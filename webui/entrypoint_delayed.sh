#!/bin/bash
# Entrypoint for nanobot-webui with DELAYED Hybrid Server
# Stage 0 用 Vision API，然后 Hybrid 根据 GPU 自动选择 cuda/cpu

echo "============================================================"
echo "🚀 Starting Nanobot WebUI (Delayed Hybrid Mode)"
echo "============================================================"

echo "ℹ️ Stage 0: Vision API 先运行 (qwen3.5:9b)"
echo "ℹ️ Hybrid 将在 Vision 完成后启动（GPU/CPU 自动检测）"

# 创建 Hybrid 启动脚本（由 pipeline.py 调用）
echo "📝 创建 Hybrid 启动脚本..."
cat > /tmp/start_hybrid.sh << 'HYBRID_SCRIPT'
#!/bin/bash
# 启动 Hybrid 服务（由 pipeline.py 调用）
# 自动检测 GPU：有 GPU → cuda，无 GPU → cpu

if pgrep -f "opendataloader-pdf-hybrid" > /dev/null; then
    echo "Hybrid already running"
    exit 0
fi

# 检测 GPU
DEVICE="cpu"
if nvidia-smi > /dev/null 2>&1; then
    DEVICE="cuda"
    echo "✅ GPU detected, using CUDA"
else
    echo "ℹ️ No GPU detected, using CPU"
fi

echo "Starting Hybrid Server ($DEVICE)..."
nohup opendataloader-pdf-hybrid --port 5002 --device $DEVICE --log-level info > /tmp/hybrid.log 2>&1 &
HYBRID_PID=$!
echo "Hybrid PID: $HYBRID_PID (device=$DEVICE)"

MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s http://localhost:5002/health > /dev/null 2>&1; then
        echo "Hybrid ready (device=$DEVICE)"
        exit 0
    fi
    sleep 1
    WAITED=$((WAITED + 1))
done

echo "Hybrid not ready after $MAX_WAIT seconds"
exit 1
HYBRID_SCRIPT

chmod +x /tmp/start_hybrid.sh
echo "✅ Hybrid 启动脚本已创建: /tmp/start_hybrid.sh (GPU/CPU 自动检测)"

# Start WebUI (Hybrid 未启动，GPU 空闲给 Vision API)
echo "============================================================"
echo "🌐 Starting WebUI Application..."
echo "============================================================"

exec python -m app.main