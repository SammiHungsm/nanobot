# SFC AI 財報分析系統 - 完整部署指南

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                       │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ financial_     │  │ knowledge_   │  │ document_       │  │
│  │ metrics        │  │ graph        │  │ chunks (JSONB)  │  │
│  └────────────────┘  └──────────────┘  └─────────────────┘  │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ raw_artifacts  │  │ documents    │  │ processing_     │  │
│  │ (file paths)   │  │ (master)     │  │ queue           │  │
│  └────────────────┘  └──────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────┴────────┐  ┌──────┴───────┐  ┌────────┴────────┐
│ OpenDataLoader │  │  Vanna AI    │  │  Nanobot        │
│ (PDF Parser)   │  │  (Text2SQL)  │  │  (Agent Layer)  │
└────────────────┘  └──────────────┘  └─────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│      Docker Volume (Raw Data Storage)   │
│  /app/data/raw/                         │
│  ├── doc_001/                           │
│  │   ├── image_001.png                  │
│  │   ├── image_002.png                  │
│  │   ├── table_001.json                 │
│  │   └── layered_001.pdf                │
│  └── doc_002/                           │
└─────────────────────────────────────────┘
```

## 🎯 核心特性

### 1. **100% Auditability (完全可追溯)**
- 所有財務數字都有 source_page 和 source_table_id
- Raw Images 和 Tables 永久保存
- 用戶查詢時可展示原始圖片 (有圖有真相)

### 2. **PostgreSQL Only (單一數據庫)**
- 使用 `JSONB` 存儲非結構化數據
- 使用 `pgvector` 支持 Hybrid Search (可選)
- Data Consistency 極高，維護簡單

### 3. **CPU/GPU 兼容 (統一 Docker 環境)**
- **CPU 用家**: 使用 API 模式 (DashScope / OpenAI)
- **GPU 用家**: 使用 Local 模式 (vLLM / Ollama)
- 同一個 Docker Compose，通過 `.env` 配置切換

### 4. **OpenDataLoader Integration**
- 解析 PDF 提取文字、表格、圖片
- 保存所有 Raw Data 到 Docker Volume
- DB 只存路徑，不存二進制 (高效)

---

## 📋 部署步驟

### Step 1: 克隆項目

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot
```

### Step 2: 配置環境變量

複製 `.env.example` 到 `.env`:

```bash
cp .env.example .env
```

**CPU 用家配置** (使用 API):
```ini
LLM_BACKEND=api
DASHSCOPE_API_KEY=sk-your-api-key-here
DATABASE_URL=postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports
DATA_DIR=/app/data/raw
```

**GPU 用家配置** (使用本地 GPU):
```ini
LLM_BACKEND=local
VLLM_PORT=5000
VLLM_MODEL=Qwen/Qwen2.5-VL-7B-Instruct
USE_CUDA=true
TORCH_DEVICE=cuda
DATABASE_URL=postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports
DATA_DIR=/app/data/raw
```

### Step 3: 啟動服務

**CPU 用家**:
```bash
docker-compose up -d
```

**GPU 用家**:
```bash
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

### Step 4: 驗證服務

```bash
# 檢查所有容器狀態
docker-compose ps

# 查看日誌
docker-compose logs -f postgres-financial
docker-compose logs -f nanobot-gateway
docker-compose logs -f vanna-service
```

---

## 📊 數據庫 Schema

### 核心表格

1. **`companies`** - 公司主數據
2. **`financial_metrics`** - 結構化財務數字 (Vanna 查詢目標)
3. **`knowledge_graph`** - 實體與關係 (JSONB 存儲)
4. **`document_chunks`** - 非結構化文本 (JSONB + pgvector)
5. **`raw_artifacts`** - Raw Data 路徑追蹤
6. **`documents`** - 文檔主表

### 查看 Schema

```bash
docker-compose exec postgres-financial psql -U postgres -d annual_reports -c "\dt"
```

---

## 📥 導入 PDF 文檔

### 方法 1: 批量導入

將 PDF 放入輸入目錄:
```bash
cp your_reports/*.pdf C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/LightRAG/data/input/__enqueued__/
```

運行批量處理器:
```bash
docker-compose run --rm nanobot-gateway \
    python -m nanobot.ingestion.batch_processor
```

### 方法 2: Watch Mode (持續監控)

```bash
docker-compose run --rm nanobot-gateway \
    python -m nanobot.ingestion.batch_processor --watch
```

### 方法 3: 手動 API 調用

```python
from nanobot.ingestion import OpenDataLoaderProcessor

processor = OpenDataLoaderProcessor(
    db_url="postgresql://postgres:password@localhost:5433/annual_reports",
    data_dir="./data/raw"
)

await processor.connect()
result = await processor.process_pdf(
    pdf_path="./report.pdf",
    company_id=1,
    doc_id="company_001_2023"
)
await processor.close()
```

---

## 🔍 查詢示例

### Vanna Text-to-SQL

```python
from nanobot.agent.tools import VannaSQL

vanna = VannaSQL(
    database_url="postgresql://postgres:password@localhost:5433/annual_reports",
    model_name="financial-sql"
)

# 用戶提問
question = "2023 年腾讯的營收是多少？"

# 生成 SQL
sql = vanna.generate_sql(question)
print(f"Generated SQL: {sql}")

# 執行查詢
result = vanna.execute(sql)
print(f"Result: {result}")
```

### 直接 SQL 查詢

```sql
-- 查詢某公司的財務指標
SELECT 
    c.name_en,
    c.name_zh,
    m.year,
    m.metric_name,
    m.value,
    m.unit
FROM financial_metrics m
JOIN companies c ON m.company_id = c.id
WHERE c.stock_code = '0700.HK'
  AND m.year = 2023
  AND m.category = 'revenue'
ORDER BY m.fiscal_period;

-- 查詢知識圖譜中的人物
SELECT 
    entity_name,
    entity_name_zh,
    attributes->>'title' AS title,
    source_file
FROM knowledge_graph
WHERE entity_type = 'person'
  AND company_id = 1
ORDER BY entity_name;

-- 查詢某文檔的所有 Raw Artifacts
SELECT 
    artifact_id,
    file_type,
    file_path,
    metadata->>'caption' AS caption,
    page_num
FROM raw_artifacts
WHERE doc_id = 'company_001_2023'
ORDER BY page_num, file_type;
```

---

## 🛠️ 開發者指南

### 項目結構

```
nanobot/
├── nanobot/
│   ├── ingestion/              # PDF 導入模塊
│   │   ├── __init__.py
│   │   ├── opendataloader_processor.py
│   │   └── batch_processor.py
│   ├── agent/
│   │   └── tools/
│   │       └── vanna_tool.py   # Vanna 集成
│   └── ...
├── storage/
│   ├── init.sql                # 簡化版 Schema
│   └── init_complete.sql       # 完整版 Schema
├── vanna-service/
│   ├── Dockerfile
│   └── start.py
├── webui/
│   ├── main.py
│   └── chat_logic.py
├── config/
│   └── config.json
├── docker-compose.yml
├── docker-compose.gpu.yml
└── .env.example
```

### 本地開發

1. 安裝依賴:
```bash
pip install -e .
```

2. 運行測試:
```bash
pytest tests/
```

3. 熱重載開發:
```bash
docker-compose up --build
```

---

## 🚨 故障排查

### 數據庫連接失敗

```bash
# 檢查 PostgreSQL 是否運行
docker-compose ps postgres-financial

# 查看日誌
docker-compose logs postgres-financial

# 重啟服務
docker-compose restart postgres-financial
```

### Vanna 訓練失敗

```bash
# 進入容器
docker-compose exec vanna-service bash

# 手動運行訓練
python -c "from nanobot.agent.tools.vanna_tool import VannaSQL; v = VannaSQL(); print(v.train_schema(force=True))"
```

### OpenDataLoader 解析錯誤

檢查日誌:
```bash
docker-compose logs nanobot-gateway | grep -i "opendataloader"
```

---

## 📈 性能優化

### 1. 並行處理

在 `.env` 中調整:
```ini
MAX_CONCURRENT_TASKS=10
BATCH_SIZE=20
```

### 2. 批量插入

使用 `asyncpg` 的 `executemany` 進行批量插入:
```python
await conn.executemany(
    """
    INSERT INTO financial_metrics (...) VALUES (...)
    """,
    records
)
```

### 3. 索引優化

定期分析表:
```sql
ANALYZE financial_metrics;
ANALYZE knowledge_graph;
ANALYZE document_chunks;
```

---

## 🔒 安全建議

1. **修改默認密碼**:
   - 編輯 `.env` 中的 `POSTGRES_PASSWORD`
   - 更新 `docker-compose.yml`

2. **限制網絡訪問**:
   - PostgreSQL 只暴露給內部網絡
   - 使用 Docker 網絡隔離

3. **定期備份**:
   ```bash
   docker-compose exec postgres-financial pg_dump -U postgres annual_reports > backup.sql
   ```

---

## 📚 參考文檔

- [PostgreSQL JSONB 文檔](https://www.postgresql.org/docs/current/datatype-json.html)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [Vanna AI 文檔](https://vanna.ai/docs/)
- [OpenDataLoader 文檔](https://github.com/openclaw/opendataloader)

---

## 🤝 貢獻指南

詳見 [CONTRIBUTING.md](./CONTRIBUTING.md)

---

## 📄 License

MIT License - 詳見 [LICENSE](./LICENSE)

---

## 📞 支持

如有問題，請:
1. 查看本部署指南
2. 檢查故障排查章節
3. 提交 GitHub Issue

**Happy Analyzing! 📊✨**
