# Vanna 服務升級完成！🎉

## 完成的修改

### 1. **Vanna Service (`vanna-service/start.py`)**
已從「空殼」升級為完整的 REST API 服務，包含：

**核心功能：**
- ✅ 初始化 Vanna AI (ChromaDB + OpenAI)
- ✅ 自動連接 PostgreSQL 並學習 Database Schema
- ✅ 提供 REST API 端點供其他服務調用
- ✅ 支持「邊做邊學」(Continuous Learning)

**API 端點：**

| 端點 | 方法 | 功能 |
|------|------|------|
| `/health` | GET | 健康檢查 |
| `/status` | GET | 獲取服務狀態 |
| `/api/train` | POST | 觸發訓練 (支持全庫或特定文件) |
| `/api/ask` | POST | 自然語言問答 (Text-to-SQL) |
| `/api/train/ddl` | POST | 直接提供 DDL 訓練 |
| `/api/train/sql` | POST | 提供問題+SQL 範例訓練 |

**請求範例：**
```bash
# 觸發訓練
curl -X POST http://localhost:8082/api/train \
  -H "Content-Type: application/json" \
  -d '{"train_type": "schema"}'

# 針對特定文件訓練
curl -X POST http://localhost:8082/api/train \
  -H "Content-Type: application/json" \
  -d '{"train_type": "sql", "doc_id": "apple_2024_annual"}'

# 問問題
curl -X POST http://localhost:8082/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Apple 2024 年的營收是多少？", "include_sql": true}'
```

---

### 2. **Vanna Dockerfile (`vanna-service/Dockerfile`)**
- ✅ 添加 `fastapi` 和 `uvicorn` 依賴
- ✅ 暴露端口 `8082`
- ✅ 更新健康檢查使用 HTTP 端點
- ✅ 創建持久化目錄 (`/app/data/chromadb`)

---

### 3. **OpenDataLoader Processor (`nanobot/ingestion/opendataloader_processor.py`)**
- ✅ 添加 `httpx` 依賴用於 HTTP 請求
- ✅ 添加 `_trigger_vanna_training()` 方法
- ✅ 在 `process_pdf()` 完成後自動觸發 Vanna 訓練

**自動訓練流程：**
```
PDF 上傳 → 解析 → 存入 PostgreSQL → 自動觸發 Vanna 訓練 → 完成！
```

---

## 「邊做邊學」架構圖

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  PDF Ingestion  │         │   PostgreSQL     │         │  Vanna Service  │
│    Processor    │────────▶│  (documents,     │         │   (FastAPI)     │
│                 │  Write  │   chunks,        │         │                 │
│                 │         │   artifacts)     │         │                 │
└─────────────────┘         └──────────────────┘         └─────────────────┘
         │                                                  ▲
         │                                                  │
         │              POST /api/train                     │
         └──────────────────────────────────────────────────┘
                   觸發訓練 (doc_id)
                   
┌─────────────────┐         ┌──────────────────┐
│     WebUI       │         │   Vanna Service  │
│   (Chat Agent)  │────────▶│   (Text-to-SQL)  │
│                 │  Question                   │
│                 │◀────────│  SQL + Answer     │
└─────────────────┘         └──────────────────┘
```

---

## 測試步驟

### 1. 重新 Build Docker
```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot
docker compose down
docker compose up -d --build
```

### 2. 檢查服務狀態
```bash
# 查看日誌
docker compose logs -f vanna-service

# 健康檢查
curl http://localhost:8082/health
```

### 3. 測試自動訓練流程

**步驟 A：上傳 PDF**
```bash
# 使用你的 WebUI 或 CLI 上傳 PDF
# 例如：
nanobot ingest --file ./apple_2024_annual_report.pdf --company-id 1
```

**步驟 B：查看訓練日誌**
```bash
# 應該看到類似輸出：
# 📖 正在使用 OpenDataLoader 真實解析 PDF...
# ✅ 真實解析完成：共提取了 150 個 artifacts
# 💾 保存完成：{'total_chunks': 120, 'total_tables': 25, 'total_images': 5}
# 🧠 正在觸發 Vanna 訓練 (doc_id: apple_2024_annual)...
# ✅ Vanna 訓練已觸發：Vanna is learning document apple_2024_annual in background.
```

**步驟 C：測試問答**
```bash
# 直接問 Vanna 服務
curl -X POST http://localhost:8082/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "這份財報中有哪些主要財務指標？"}'

# 或通過 WebUI 提問
```

---

## 環境變量配置

在 `docker-compose.yml` 或 `.env` 中添加：

```yaml
services:
  vanna-service:
    environment:
      - OPENAI_API_KEY=sk-xxxxxxxxxxxxxx  # 必填
      - VANNA_MODEL=gpt-4o-mini           # 可選，預設 gpt-4o-mini
      - VANNA_PORT=8082
      - DATABASE_URL=postgresql://postgres:password@postgres-financial:5432/annual_reports
  
  # PDF Ingestion Worker 需要知道 Vanna Service 的位置
  ingestion-worker:
    environment:
      - VANNA_SERVICE_URL=http://vanna-service:8082
```

---

## 注意事項

### 1. **OpenAI API Key**
Vanna 需要 OpenAI API Key 才能運作。如果沒有設置：
- 服務會啟動但在「Mock Mode」下運行
- API 會返回示範回應，不會真正生成 SQL

### 2. **ChromaDB 持久化**
- 訓練資料會保存在 `/app/data/chromadb` 目錄
- 建議將此目錄掛載到 Docker Volume，避免重啟後丟失訓練資料

### 3. **訓練策略建議**
- **初次啟動**: 自動學習所有 Table Schema
- **新增文件**: 通過 `/api/train` 觸發特定文件訓練
- **定期優化**: 可以定期調用 `/api/train?train_type=schema` 更新結構

### 4. **性能優化**
- 背景訓練：使用 `BackgroundTasks` 避免阻塞 API 請求
- 異步處理：PDF 解析使用 `asyncio.to_thread` 避免阻塞主線程

---

## 下一步擴展

1. **添加訓練歷史記錄**: 記錄每次訓練的時間、文件、結果
2. **SQL 反饋機制**: 讓使用者可以標記 SQL 是否正確，用於改進訓練
3. **批量訓練**: 支持一次訓練多個文件
4. **訓練進度查詢**: 添加 `/api/train/status` 端點查詢訓練進度

---

## 故障排除

### Q: Vanna Service 無法啟動？
```bash
# 檢查日誌
docker compose logs vanna-service

# 常見問題：
# 1. OPENAI_API_KEY 未設置
# 2. 數據庫連接失敗
# 3. 端口被佔用
```

### Q: 訓練請求失敗？
```bash
# 檢查 Vanna Service 是否可達
curl http://vanna-service:8082/health

# 檢查數據庫連接
docker compose exec vanna-service python -c "import psycopg2; psycopg2.connect('your_db_url')"
```

### Q: 問答不準確？
- 確保已正確訓練 Database Schema
- 添加更多 SQL 範例：`POST /api/train/sql`
- 檢查 OpenAI Model 是否合適（嘗試 gpt-4o 而非 gpt-4o-mini）

---

**恭喜！你的 Vanna Service 現在已經是完全體的「邊做邊學」RAG 引擎了！** 🚀
