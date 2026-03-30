# 🚀 Nanobot 快速開始指南

**5 分鐘內啟動你的 AI 財報分析系統！**

---

## 📋 前置要求

### 必須安裝

- ✅ **Docker Desktop** (Windows/Mac)
  - 下載：https://www.docker.com/products/docker-desktop
  - 安裝後重啟電腦

### 可選工具

- Git (用於克隆倉庫)
- Python 3.11+ (用於本地開發)
- uv (快速 Python 包管理器)

---

## 🎯 快速啟動 (3 步)

### 步驟 1: 準備 PDF 文件

將你的財報 PDF 文件放到一個文件夾，例如：
```
C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\pdfs\
```

### 步驟 2: 運行一鍵部署

**Windows PowerShell:**
```powershell
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot
.\deploy.ps1
```

**如果部署腳本無法運行，手動執行：**
```powershell
# 1. 停止現有容器
docker-compose down

# 2. 構建鏡像
docker-compose build --no-cache

# 3. 啟動服務
docker-compose up -d

# 4. 等待 60 秒
Start-Sleep -Seconds 60

# 5. 檢查狀態
docker-compose ps
```

### 步驟 3: 訪問 Web UI

打開瀏覽器，訪問：**http://localhost:3000**

---

## ✅ 驗證部署

### 檢查服務狀態

```powershell
# 查看所有容器
docker-compose ps

# 應該看到：
# NAME                   STATUS         PORTS
# mongodb-docs           Up (healthy)   27018->27017
# nanobot-gateway        Up             8081, 18790
# nanobot-webui          Up             0.0.0.0:3000->8080
# postgres-financial     Up (healthy)   5433->5432
```

### 運行測試

```powershell
# 進入容器運行測試
docker exec -it nanobot-gateway python test_docker_integration.py
```

---

## 🎓 第一次使用

### 1. 訓練 Vanna (首次必須做)

```powershell
docker exec -it nanobot-gateway python train_vanna.py
```

預期輸出：
```
✓ Database connected
✓ Schema training completed
  - DDL statements: 3
  - Documentation: 6
  - Example queries: 4
✅ TRAINING COMPLETE
```

### 2. 建立 PDF 索引

```powershell
# 替換你的 PDF 文件路徑
docker exec -it nanobot-gateway python nanobot/skills/document_indexer/scripts/build_indexes.py /data/pdfs/your_report.pdf
```

預期輸出：
```
🚀 地圖已存儲：/app/workspace/indexes/your_report
   📑 目錄章節：15 個
   📊 提取表格：8 個
   📄 PDF 頁數：120 頁
   ✨ 使用 OpenDataLoader 解析
```

### 3. 開始對話

訪問 **http://localhost:3000**，然後：

1. 在左側邊欄選擇剛才建立索引的文件
2. 或者上傳新的 PDF 文件
3. 開始提問，例如：
   - "Show the revenue for 2023"
   - "What is the company's main business?"
   - "Compare revenue growth year-over-year"

---

## 🔧 常用命令

### 查看日誌

```powershell
# 實時查看所有服務日誌
docker-compose logs -f

# 查看特定服務日誌
docker-compose logs -f nanobot-gateway
docker-compose logs -f nanobot-webui
```

### 重啟服務

```powershell
# 重啟所有服務
docker-compose restart

# 重啟特定服務
docker-compose restart nanobot-gateway
```

### 停止服務

```powershell
# 停止所有服務
docker-compose down

# 停止並刪除數據 (小心！)
docker-compose down -v
```

### 進入容器

```powershell
# 進入 Nanobot Gateway 容器
docker exec -it nanobot-gateway bash

# 在容器內可以運行：
python train_vanna.py
python test_docker_integration.py
python nanobot/skills/document_indexer/scripts/build_indexes.py /data/pdfs/report.pdf
```

---

## 📊 系統架構

```
┌────────────────────────────────────────────┐
│            Your Browser                    │
│         http://localhost:3000              │
└──────────────┬─────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────┐
│         Nanobot Web UI                     │
│         (Port 3000)                        │
└──────────────┬─────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────┐
│       Nanobot Gateway                      │
│       (Port 8081)                          │
│  ┌─────────────┐  ┌──────────────────┐   │
│  │  Vanna AI   │  │  Intent Router   │   │
│  └─────────────┘  └──────────────────┘   │
└──────┬─────────────────────┬──────────────┘
       │                     │
       ▼                     ▼
┌──────────────┐    ┌──────────────────┐
│  PostgreSQL  │    │   MongoDB        │
│  (Port 5433) │    │   (Port 27018)   │
│              │    │                  │
│  - companies │    │  - documents     │
│  - metrics   │    │  - text_search   │
└──────────────┘    └──────────────────┘
```

---

## ❓ 常見問題

### Q1: Web UI 打唔開？

**檢查:**
```powershell
# 檢查 Web UI 容器狀態
docker-compose ps nanobot-webui

# 查看 Web UI 日誌
docker-compose logs nanobot-webui

# 檢查端口占用
netstat -ano | findstr :3000
```

**解決方案:**
```powershell
# 重啟 Web UI
docker-compose restart nanobot-webui
```

### Q2: 數據庫連接失敗？

**檢查:**
```powershell
# 檢查 PostgreSQL 狀態
docker exec postgres-financial pg_isready -U postgres

# 檢查 MongoDB 狀態
docker exec mongodb-docs mongosh --eval "db.runCommand('ping')"
```

**解決方案:**
```powershell
# 重啟數據庫
docker-compose restart postgres-financial mongodb-docs
```

### Q3: PDF 文件搵唔到？

**檢查:**
```powershell
# 進入容器查看
docker exec -it nanobot-gateway ls -la /data/pdfs/
```

**解決方案:**
1. 檢查 `docker-compose.yml` 中嘅 volumes 配置
2. 確保 PDF 路徑正確：
```yaml
volumes:
  - "C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/pdfs:/data/pdfs"
```
3. 重啟容器：`docker-compose restart nanobot-gateway`

### Q4: Vanna 訓練失敗？

**檢查:**
```powershell
# 檢查數據庫是否有表
docker exec postgres-financial psql -U postgres -d annual_reports -c "\dt"
```

**解決方案:**
```powershell
# 如果表不存在，檢查 init.sql
docker exec postgres-financial psql -U postgres -d annual_reports -f /docker-entrypoint-initdb.d/init.sql

# 重新訓練
docker exec -it nanobot-gateway python train_vanna.py
```

---

## 🎯 下一步

### 1. 配置你的環境

創建 `.env` 文件：
```bash
# 數據庫密碼
POSTGRES_PASSWORD=your_secure_password
MONGODB_PASSWORD=your_secure_password

# PDF 文件路徑
PDF_DATA_DIR=C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/pdfs
```

### 2. 添加更多 PDF 文件

```powershell
# 將 PDF 複製到掛載的文件夾
copy "C:\path\to\your\report.pdf" "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\pdfs\"

# 重新啟動容器
docker-compose restart nanobot-gateway

# 建立索引
docker exec -it nanobot-gateway python nanobot/skills/document_indexer/scripts/build_indexes.py /data/pdfs/report.pdf
```

### 3. 自定義配置

編輯 `config/config.yaml` 或 `config/config.json`：
```yaml
model:
  provider: openai
  name: gpt-4o

channels:
  webchat:
    enabled: true
    port: 8080
```

### 4. 備份數據庫

```powershell
# 備份 PostgreSQL
docker exec postgres-financial pg_dump -U postgres annual_reports > backup_$(Get-Date -Format "yyyyMMdd").sql

# 備份 MongoDB
docker exec mongodb-docs mongodump --username mongo --password mongo_password_change_me --out /backup
```

---

## 📚 更多文檔

- [完整部署指南](DOCKER_DEPLOYMENT.md)
- [修復報告](FIXES_COMPLETED.md)
- [Docker 故障排除](DOCKER_DEPLOYMENT.md#故障排除)

---

## 🆘 需要幫助？

如果遇到問題：

1. 查看日誌：`docker-compose logs -f`
2. 運行測試：`docker exec -it nanobot-gateway python test_docker_integration.py`
3. 查看 [故障排除指南](DOCKER_DEPLOYMENT.md#故障排除)

---

**祝你使用愉快！** 🎉

如果一切正常，你而家可以：
- 訪問 Web UI: http://localhost:3000
- 上傳財報 PDF
- 用自然語言提問財務數據
