#!/bin/bash
# WebUI 測試和啟動腳本

echo "=========================================="
echo "  Nanobot WebUI - 測試和啟動"
echo "=========================================="

# 設置環境變量
export LOG_LEVEL=DEBUG
export DATABASE_URL="postgresql://postgres:postgres_password_change_me@localhost:5432/annual_reports"

# 檢查依賴
echo ""
echo "📦 檢查依賴..."
pip install fastapi uvicorn python-multipart loguru aiohttp --quiet

# 創建必要的目錄
echo ""
echo "📁 創建目錄..."
mkdir -p logs data/uploads

# 檢查端口
echo ""
echo "🔍 檢查端口 8080..."
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  端口 8080 已被使用，嘗試終止..."
    lsof -ti:8080 | xargs kill -9 2>/dev/null || true
fi

# 啟動服務器
echo ""
echo "🚀 啟動 WebUI 服務器..."
echo ""
echo "  📍 URL: http://localhost:8080"
echo "  📍 API Docs: http://localhost:8080/docs"
echo "  📍 日誌級別: DEBUG"
echo ""
echo "按 Ctrl+C 停止服務器"
echo "=========================================="

cd "$(dirname "$0")"
python -m uvicorn webui.app.main:app --host 0.0.0.0 --port 8080 --reload --log-level debug