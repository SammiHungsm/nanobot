# WebUI 修復指南 - 2026-03-31

本次修復解決了三個核心問題：
1. **PDF 假處理問題** - PDF 只上傳但沒有真正解析、沒有進 DB 和 Vanna
2. **Chat 壞掉問題** - 聊天功能無反應
3. **缺少 Database Tab** - 無法查看已解析的數據庫數據

---

## 🔧 修復內容總覽

### 1. PDF 處理修復 (`document_service.py`)

**問題根源：**
- WebUI 使用 `pdf_service.py` 中的 mock result，當找不到 OpenDataLoader 時返回空數據
- 沒有調用真正的 `OpenDataLoaderProcessor` 來處理 PDF、寫入 PostgreSQL 和觸發 Vanna

**修復內容：**
- 修改 `webui/app/services/document_service.py`
- 導入 `nanobot.ingestion.opendataloader_processor.OpenDataLoaderProcessor`
- 將原本的 `process_pdf_async` 替換為真實的處理器
- 現在會：解析 PDF → 存入 PostgreSQL → 觸發 Vanna 訓練

**修改的文件：**
- [`webui/app/services/document_service.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/app/services/document_service.py)

---

### 2. Chat 功能修復 (`chat.py`)

**問題根源：**
- WebUI 的 `/api/chat/stream` 端點沒有轉發請求到 Gateway (8081)
- Gateway URL 可能配置錯誤（例如使用 localhost 而非 Docker 服務名稱）

**修復內容：**
- 修改 `webui/app/api/chat.py`
- 添加 `GATEWAY_URL` 環境變數（預設：`http://nanobot-gateway:8081`）
- 實現請求轉發邏輯：
  - 非流式請求：`POST /api/chat` → 轉發到 Gateway 並返回回應
  - 流式請求：`POST /api/stream` → 使用 `httpx` 流式轉發

**修改的文件：**
- [`webui/app/api/chat.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/app/api/chat.py)

---

### 3. 新增 Database Tab

**功能描述：**
- 新增第三個分頁，用於查看 PostgreSQL 中的已解析數據
- 顯示統計數據：文檔數量、Chunks 數量、表格數量、圖片數量
- 顯示最近的 document chunks 列表

**新增的文件：**
- [`webui/app/api/database.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/app/api/database.py) - Database API Router
  - `GET /api/database/stats` - 獲取統計數據
  - `GET /api/database/chunks` - 獲取最近的 chunks
  - `GET /api/database/documents` - 獲取所有文檔

**修改的文件：**
- [`webui/static/index.html`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/static/index.html) - 新增 Database Tab UI
- [`webui/static/js/app.js`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/static/js/app.js) - 新增分頁切換邏輯和數據載入
- [`webui/app/main.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/app/main.py) - 註冊 Database Router
- [`webui/app/api/__init__.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/app/api/__init__.py) - 導出新的 router

---

### 4. Docker Compose 配置更新

**修改的文件：**
- [`docker-compose.yml`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/docker-compose.yml)

**更新內容：**
```yaml
nanobot-webui:
  environment:
    - GATEWAY_URL=http://nanobot-gateway:8081  # 新增
    - DATA_DIR=/app/data/raw                   # 新增
  volumes:
    - ./data/raw:/app/data/raw                 # 新增
```

---

### 5. 依賴更新

**修改的文件：**
- [`webui/requirements.txt`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/requirements.txt)

**新增依賴：**
```
asyncpg==0.29.0  # PostgreSQL 異步驅動
```

---

## 🚀 部署步驟

### 1. 重新構建 Docker 映像

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot

# 重新構建 WebUI (包含新依賴)
docker-compose build nanobot-webui

# 或者重新構建所有服務
docker-compose build
```

### 2. 重啟服務

```bash
# 重啟 WebUI
docker-compose restart nanobot-webui

# 或者重啟所有服務
docker-compose down
docker-compose up -d
```

### 3. 驗證修復

#### 測試 PDF 處理
1. 訪問 http://localhost:3000
2. 切換到 "PDF Library" Tab
3. 上傳一個 PDF 文件
4. 查看 Processing Log，應該看到：
   - `Extracting with OpenDataLoader`
   - `DB insertion & Vanna sync complete`
   - `✅ Processing complete`

#### 測試 Chat 功能
1. 在 Chat Tab 輸入問題
2. 應該能看到 AI 回應
3. 檢查 Log，確認請求已轉發到 Gateway

#### 測試 Database Tab
1. 切換到 "Database Data" Tab
2. 點擊 "Refresh Stats"
3. 應該能看到統計數據和最近的 chunks

---

## 🔍 故障排查

### PDF 處理仍然失敗

檢查 WebUI Log：
```bash
docker logs nanobot-webui --tail 100
```

確認環境變數：
```bash
docker exec nanobot-webui env | grep DATABASE_URL
```

### Chat 無回應

檢查 Gateway 是否運行：
```bash
docker ps | grep nanobot-gateway
```

測試 Gateway 連接：
```bash
docker exec nanobot-webui curl http://nanobot-gateway:8081/health
```

### Database Tab 顯示錯誤

確認 PostgreSQL 連接：
```bash
docker exec nanobot-webui python -c "import asyncpg; print('OK')"
```

檢查數據庫表是否存在：
```bash
docker exec postgres-financial psql -U postgres -d annual_reports -c "\dt"
```

---

## 📊 架構圖

```
┌─────────────────┐
│   Web Browser   │
│  localhost:3000 │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│        Nanobot WebUI (Port 8080)        │
│  ┌─────────────────────────────────┐    │
│  │  /api/chat                      │    │
│  │  ├─ POST /api/chat → Gateway    │    │
│  │  └─ POST /api/stream → Gateway  │    │
│  ├─────────────────────────────────┤    │
│  │  /api/documents                 │    │
│  │  └─ PDF Upload & Processing     │    │
│  │     → OpenDataLoaderProcessor   │    │
│  ├─────────────────────────────────┤    │
│  │  /api/database (NEW!)           │    │
│  │  ├─ GET /stats                  │    │
│  │  ├─ GET /chunks                 │    │
│  │  └─ GET /documents              │    │
│  └─────────────────────────────────┘    │
└────────────┬────────────────────────────┘
             │
    ┌────────┼────────┐
    │        │        │
    ▼        ▼        ▼
┌─────────┐ ┌─────────────────┐ ┌──────────────┐
│ Gateway │ │   PostgreSQL    │ │ Vanna Service│
│ :8081   │ │   :5432         │ │    :8082     │
│  (LLM)  │ │ (Financial DB)  │ │ (Text-to-SQL)│
└─────────┘ └─────────────────┘ └──────────────┘
```

---

## ✅ 完成清單

- [x] 修改 `document_service.py` 使用真實的 `OpenDataLoaderProcessor`
- [x] 修改 `chat.py` 實現 Gateway 請求轉發
- [x] 新增 `database.py` API Router
- [x] 新增 Database Tab UI (`index.html`)
- [x] 更新 `app.js` 支持三分頁切換
- [x] 更新 `main.py` 註冊 Database Router
- [x] 更新 `docker-compose.yml` 添加環境變數
- [x] 更新 `requirements.txt` 添加 `asyncpg`
- [x] 更新 `api/__init__.py` 導出新 router

---

## 📝 注意事項

1. **數據庫連接字符串**：確保 `DATABASE_URL` 正確指向 `postgres-financial:5432`
2. **Gateway 服務名稱**：Docker Compose 中使用 `nanobot-gateway` 而非 `localhost`
3. **Volume 掛載**：確保 `./data/raw` 目錄存在且有寫入權限
4. **依賴安裝**：重新構建鏡像以安裝 `asyncpg`

---

**修復完成日期：** 2026-03-31  
**修復版本：** v2.1.0
