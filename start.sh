#!/bin/bash
# SFC AI 財報分析系統 - 啟動腳本

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "============================================="
echo "SFC AI 財報分析系統"
echo "============================================="
echo ""

# 檢查 .env 文件
if [ ! -f ".env" ]; then
    echo "⚠️  未找到 .env 文件"
    echo "📝 建議：複製 .env.example 並修改配置"
    echo ""
    if [ -f ".env.example" ]; then
        read -p "是否自動創建 .env 文件？(y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cp .env.example .env
            echo "✅ 已創建 .env 文件，請修改後重啟"
            exit 0
        fi
    fi
fi

# 停止舊容器
echo "🛑 停止舊容器..."
docker-compose down 2>/dev/null || true

# 啟動服務
echo "🚀 啟動服務..."
docker-compose up -d

# 等待服務就緒
echo ""
echo "⏳ 等待服務就緒..."
sleep 10

# 檢查服務狀態
echo ""
echo "📊 服務狀態:"
docker-compose ps

# 初始化 MongoDB 索引
echo ""
echo "📝 初始化 MongoDB 索引..."
docker-compose exec -T nanobot-gateway python /app/scripts/init_mongodb.py || {
    echo "⚠️  MongoDB 初始化失敗，可以手動執行："
    echo "   docker-compose exec nanobot-gateway python /app/scripts/init_mongodb.py"
}

echo ""
echo "============================================="
echo "✅ 啟動完成！"
echo "============================================="
echo ""
echo "服務列表:"
echo "  - PostgreSQL:   localhost:5433"
echo "  - MongoDB:      localhost:27018"
echo "  - Nanobot:      localhost:18790"
echo "  - Web UI:       localhost:3000"
echo ""
echo "查看日誌："
echo "  docker-compose logs -f nanobot-gateway"
echo ""
echo "停止服務："
echo "  docker-compose down"
echo ""
