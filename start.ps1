# SFC AI 財報分析系統 - Quick Start Script
# Windows PowerShell

param(
    [string]$Mode = "up",  # up, down, restart, rebuild
    [switch]$GPU,
    [switch]$Watch
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SFC AI 財報分析系統" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 設置配置文件路徑
$COMPOSE_FILE = "docker-compose.yml"
if ($GPU) {
    Write-Host "🚀 GPU 模式已啟用" -ForegroundColor Green
    $COMPOSE_FILE = "docker-compose.yml,docker-compose.gpu.yml"
    $env:COMPOSE_FILE = $COMPOSE_FILE
} else {
    Write-Host "💻 CPU 模式" -ForegroundColor Gray
}

Write-Host ""

# 檢查 .env 文件
if (!(Test-Path ".env")) {
    Write-Host "⚠️  未找到 .env 文件，正在從 .env.example 創建..." -ForegroundColor Yellow
    
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "✅ .env 文件已創建" -ForegroundColor Green
        Write-Host ""
        Write-Host "⚠️  請編輯 .env 文件並設置以下必填變量:" -ForegroundColor Yellow
        Write-Host "   - DASHSCOPE_API_KEY (API 模式)" -ForegroundColor White
        Write-Host "   - 或設置 LLM_BACKEND=local (GPU 模式)" -ForegroundColor White
        Write-Host ""
        Write-Host "按任意鍵繼續，或按 Ctrl+C 退出..." -ForegroundColor Gray
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    } else {
        Write-Host "❌ 錯誤：找不到 .env.example" -ForegroundColor Red
        exit 1
    }
}

# 執行 Docker Compose 命令
switch ($Mode) {
    "up" {
        Write-Host "🚀 啟動服務..." -ForegroundColor Green
        
        if ($Watch) {
            # Watch mode: 啟動所有服務 + 批量處理器
            docker-compose up -d postgres-financial nanobot-gateway vanna-service webui
            
            Write-Host ""
            Write-Host "⏳ 等待數據庫就緒..." -ForegroundColor Yellow
            Start-Sleep -Seconds 10
            
            Write-Host "📥 啟動批量處理 (Watch Mode)..." -ForegroundColor Green
            docker-compose run --rm ingestion-worker python -m nanobot.ingestion.batch_processor --watch
        } else {
            # Normal mode: 只啟動基礎服務
            docker-compose up -d
            
            Write-Host ""
            Write-Host "✅ 服務已啟動!" -ForegroundColor Green
            Write-Host ""
            Write-Host "📊 查看服務狀態:" -ForegroundColor Cyan
            Write-Host "   docker-compose ps" -ForegroundColor White
            Write-Host ""
            Write-Host "📥 導入 PDF 文件:" -ForegroundColor Cyan
            Write-Host "   1. 將 PDF 放入：C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/LightRAG/data/input/__enqueued__/" -ForegroundColor White
            Write-Host "   2. 運行：docker-compose run --rm ingestion-worker" -ForegroundColor White
            Write-Host ""
            Write-Host "🌐 訪問 Web UI:" -ForegroundColor Cyan
            Write-Host "   http://localhost:3000" -ForegroundColor White
            Write-Host ""
            Write-Host "📋 查看日誌:" -ForegroundColor Cyan
            Write-Host "   docker-compose logs -f" -ForegroundColor White
        }
    }
    
    "down" {
        Write-Host "🛑 停止服務..." -ForegroundColor Yellow
        docker-compose down
        Write-Host "✅ 服務已停止" -ForegroundColor Green
    }
    
    "restart" {
        Write-Host "🔄 重啟服務..." -ForegroundColor Yellow
        docker-compose restart
        Write-Host "✅ 服務已重啟" -ForegroundColor Green
    }
    
    "rebuild" {
        Write-Host "🔨 重新構建..." -ForegroundColor Yellow
        docker-compose down
        docker-compose build --no-cache
        docker-compose up -d
        Write-Host "✅ 重新構建完成" -ForegroundColor Green
    }
    
    "logs" {
        Write-Host "📋 查看日誌..." -ForegroundColor Cyan
        docker-compose logs -f
    }
    
    default {
        Write-Host "❌ 未知模式：$Mode" -ForegroundColor Red
        Write-Host ""
        Write-Host "用法:" -ForegroundColor Cyan
        Write-Host "   .\start.ps1              # 啟動服務 (up)" -ForegroundColor White
        Write-Host "   .\start.ps1 -GPU         # GPU 模式啟動" -ForegroundColor White
        Write-Host "   .\start.ps1 -Watch       # Watch Mode (持續監控)" -ForegroundColor White
        Write-Host "   .\start.ps1 down         # 停止服務" -ForegroundColor White
        Write-Host "   .\start.ps1 restart      # 重啟服務" -ForegroundColor White
        Write-Host "   .\start.ps1 rebuild      # 重新構建" -ForegroundColor White
        Write-Host "   .\start.ps1 logs         # 查看日誌" -ForegroundColor White
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
