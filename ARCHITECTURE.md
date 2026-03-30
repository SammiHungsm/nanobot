# SFC AI 財報分析系統 - 技術架構文檔

## 📐 系統設計原則

### 1. **100% Auditability (完全可追溯性)**
- 每個財務數字都可追溯到原始 PDF 的具體頁面和表格
- 保存所有 Raw Data (圖片、表格 JSON、Layered PDF)
- 查詢結果必須附带原始圖片佐證

### 2. **PostgreSQL Only (單一數據庫架構)**
- 使用 PostgreSQL 16 + pgvector
- JSONB 存儲非結構化數據 (取代 MongoDB)
- 結構化數據用傳統 Table
- 好處：
  - Data Consistency 極高
  - 無需維護多個數據庫
  - ACID 事務支持
  - 單一備份點

### 3. **CPU/GPU 兼容 (統一部署)**
- 同一個 Docker Compose 配置
- 通過 `.env` 切換模式
- CPU 用家：API 模式 (DashScope)
- GPU 用家：Local 模式 (vLLM/Ollama)

### 4. **OpenDataLoader First**
- 所有 PDF 解析通過 OpenDataLoader
- 提取所有可能的 Raw Data
- 寧濫毋缺 (Keep Everything)

---

## 🏗️ 整體架構

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          User Interface Layer                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │   Web UI        │  │   Mobile App    │  │   API Clients           │  │
│  │   (React)       │  │   (Future)      │  │   (REST/GraphQL)        │  │
│  └────────┬────────┘  └────────┬────────┘  └────────────┬────────────┘  │
└───────────┼────────────────────┼─────────────────────────┼──────────────┘
            │                    │                         │
            └────────────────────┼─────────────────────────┘
                                 │
┌────────────────────────────────┼────────────────────────────────────────┐
│                    Agent & Query Layer (Nanobot)                        │
│  ┌──────────────────────────────┴──────────────────────────────────┐    │
│  │              Intent Router (nanobot-gateway)                     │    │
│  │   - Parse user query (Cantonese/English/中文)                    │    │
│  │   - Route to appropriate tool                                    │    │
│  │   - Aggregate results                                            │    │
│  └──────────────────────────────┬──────────────────────────────────┘    │
│                                 │                                        │
│         ┌───────────────────────┼───────────────────────┐                │
│         │                       │                       │                │
│  ┌──────┴──────────┐   ┌───────┴────────┐   ┌──────────┴────────┐       │
│  │  Vanna AI       │   │  Knowledge      │   │  File Retrieval   │       │
│  │  (Text-to-SQL)  │   │  Graph Query    │   │  (Raw Images)     │       │
│  └──────┬──────────┘   └───────┬────────┘   └──────────┬────────┘       │
└─────────┼──────────────────────┼───────────────────────┼────────────────┘
          │                      │                       │
┌─────────┼──────────────────────┼───────────────────────┼────────────────┐
│         │         Database Layer (PostgreSQL)          │                │
│  ┌──────┴──────────┐   ┌───────┴────────┐   ┌──────────┴────────┐       │
│  │ financial_      │   │ knowledge_     │   │ document_         │       │
│  │ metrics         │   │ graph          │   │ chunks            │       │
│  │ (Structured)    │   │ (JSONB)        │   │ (JSONB + Text)    │       │
│  └─────────────────┘   └────────────────┘   └───────────────────┘       │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ raw_artifacts (file paths only)                             │        │
│  │ documents (master tracking)                                  │        │
│  │ processing_queue (background jobs)                           │        │
│  └─────────────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────┘
          │
          │ (File Paths)
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  File Storage (Docker Volume)                            │
│  /app/data/raw/                                                          │
│  ├── doc_001/                          # Company A 2023 Annual Report   │
│  │   ├── image_001.png                 # Page 1 Chart                   │
│  │   ├── image_002.png                 # Page 3 Graph                   │
│  │   ├── table_001.json                # Revenue Table                  │
│  │   ├── table_002.json                # Profit Table                   │
│  │   └── layered_001.pdf               # Full PDF with layers           │
│  └── doc_002/                          # Company B 2023 Annual Report   │
│      └── ...                                                             │
└─────────────────────────────────────────────────────────────────────────┘
          ▲
          │
┌─────────┴────────────────────────────────────────────────────────────────┐
│                     Ingestion Layer (OpenDataLoader)                     │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  OpenDataLoader Processor                                         │    │
│  │  - Parse PDF (文字、表格、圖片、結構)                            │    │
│  │  - Extract Raw Data                                              │    │
│  │  - Save files to Docker Volume                                   │    │
│  │  - Update PostgreSQL with paths & metadata                       │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Batch Processor                                                  │    │
│  │  - Monitor input directory                                       │    │
│  │  - Parallel processing (configurable concurrency)                │    │
│  │  - Retry mechanism                                               │    │
│  │  - Progress tracking                                             │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────────────────┘
          ▲
          │ (PDF Files)
          │
┌─────────┴────────────────────────────────────────────────────────────────┐
│                        Input Directory                                    │
│  /data/pdfs/ (mounted volume)                                            │
│  ├── company_a_2023.pdf                                                  │
│  ├── company_b_2023.pdf                                                  │
│  └── ...                                                                 │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 🗄️ 數據庫 Schema 詳解

### 核心設計理念

**PostgreSQL JSONB vs MongoDB:**

| 特性 | PostgreSQL JSONB | MongoDB |
|------|------------------|---------|
| ACID 事務 | ✅ 完整支持 | ⚠️ 4.0+ 支持 |
| Join 能力 | ✅ 原生支持 | ⚠️ $lookup (較慢) |
| 索引 | ✅ B-Tree, GIN, GiST | ✅ 豐富 |
| 一致性 | ✅ 強一致性 | ⚠️ 最終一致性 (默認) |
| 維護成本 | ✅ 單一 DB | ❌ 需維護兩個 DB |
| 學習曲線 | ✅ SQL (熟悉) | ⚠️ NoSQL (需學習) |

**結論**: JSONB 完全滿足需求，無需 MongoDB

### 表結構詳解

#### 1. `financial_metrics` (結構化財務數據)

```sql
CREATE TABLE financial_metrics (
    -- 核心財務數據
    company_id INTEGER,      -- 外鍵 → companies
    year INTEGER,            -- 財年
    fiscal_period VARCHAR,   -- 'FY', 'H1', 'Q1'
    metric_name VARCHAR,     -- 'revenue', 'profit'
    value DOUBLE PRECISION,  -- 數值
    unit VARCHAR,            -- 'CNY', 'USD', 'percentage'
    
    -- Audit Trail (關鍵!)
    source_file VARCHAR,     -- 原始 PDF 文件名
    source_page INTEGER,     -- 頁碼
    source_table_id VARCHAR, -- 表格 ID
    extraction_confidence FLOAT,
    
    -- Validation
    validated BOOLEAN,
    validated_by VARCHAR
);
```

**用途**: Vanna Text-to-SQL 的主要查詢目標

**示例查詢**:
```sql
-- 腾讯 2023 年營收增長率
SELECT 
    (m1.value - m2.value) / m2.value * 100 AS growth_rate
FROM financial_metrics m1
JOIN financial_metrics m2 
    ON m1.company_id = m2.company_id 
    AND m1.metric_name = m2.metric_name
WHERE m1.company_id = 1
    AND m1.year = 2023
    AND m2.year = 2022
    AND m1.metric_name = 'revenue';
```

#### 2. `knowledge_graph` (實體與關係)

```sql
CREATE TABLE knowledge_graph (
    entity_type VARCHAR,     -- 'person', 'event', 'organization'
    entity_name VARCHAR,
    entity_name_zh VARCHAR,
    
    -- JSONB 存儲靈活屬性
    attributes JSONB,
    -- 示例:
    -- Person: {"title": "Chairman", "gender": "M", "age": 65}
    -- Event: {"date": "2024-03-15", "type": "AGM"}
    
    -- JSONB 存儲關係
    relations JSONB,
    -- 示例:
    -- [{"relation": "attended", "target_entity_id": 123}]
    
    -- 溯源
    company_id INTEGER,
    source_file VARCHAR,
    source_page INTEGER
);
```

**用途**: 回答「邊個係主席？」「佢出席過咩活動？」

**示例查詢**:
```sql
-- 找出所有公司的主席
SELECT 
    entity_name,
    entity_name_zh,
    attributes->>'title' AS title,
    c.name_en AS company
FROM knowledge_graph kg
JOIN companies c ON kg.company_id = c.id
WHERE entity_type = 'person'
    AND attributes->>'title' = 'Chairman';
```

#### 3. `document_chunks` (非結構化文本)

```sql
CREATE TABLE document_chunks (
    doc_id VARCHAR,          -- 文檔 ID
    company_id INTEGER,
    chunk_index INTEGER,     -- 順序
    page_num INTEGER,
    chunk_type VARCHAR,      -- 'text', 'table', 'figure_caption'
    
    content TEXT,            -- 文本內容
    content_json JSONB,      -- 結構化內容 (表格 JSON)
    metadata JSONB,          -- OpenDataLoader 元數據
    
    -- pgvector (可選)
    embedding vector(768)
);
```

**用途**: 全文搜索、混合搜索

#### 4. `raw_artifacts` (原始檔案追蹤)

```sql
CREATE TABLE raw_artifacts (
    artifact_id VARCHAR,     -- 唯一 ID
    doc_id VARCHAR,
    company_id INTEGER,
    
    file_type VARCHAR,       -- 'image', 'table_json', 'layered_pdf'
    file_path VARCHAR,       -- ⚠️ 只存路徑，不存二進制!
    
    metadata JSONB,
    -- 示例:
    -- {"caption": "Figure 1: Revenue", "page_num": 5}
    
    -- 關聯
    linked_chunk_id INTEGER, -- → document_chunks
    linked_metric_id INTEGER -- → financial_metrics
);
```

**關鍵設計**:
- **不存二進制**: 文件存 Docker Volume，DB 只存路徑
- **可追溯**: 每個 artifact 都有 source_page
- **可展示**: 查詢時可返回圖片路徑供前端展示

#### 5. `documents` (文檔主表)

```sql
CREATE TABLE documents (
    doc_id VARCHAR UNIQUE,
    company_id INTEGER,
    title VARCHAR,
    document_type VARCHAR,   -- 'annual_report', 'interim_report'
    year INTEGER,
    fiscal_period VARCHAR,
    
    file_path VARCHAR,       -- 原始 PDF 路徑
    file_hash VARCHAR,       -- SHA256 (去重)
    
    -- 處理狀態
    processing_status VARCHAR,  -- 'pending', 'processing', 'completed', 'failed'
    processing_error TEXT,
    
    -- 統計
    total_pages INTEGER,
    total_chunks INTEGER,
    total_artifacts INTEGER
);
```

---

## 🔄 數據流 Workflow

### Ingestion Flow (PDF 導入流程)

```
1. 用戶上傳 PDF
   ↓
2. Batch Processor 監控到文件
   ↓
3. OpenDataLoader 解析 PDF
   ├─ 提取文本 → document_chunks
   ├─ 提取表格 → table_XXX.json (保存文件) → raw_artifacts (存路徑)
   ├─ 提取圖片 → image_XXX.png (保存文件) → raw_artifacts (存路徑)
   └─ 提取財務數據 → financial_metrics
   ↓
4. Qwen-VL 讀取圖表
   └─ 抽取實體關係 → knowledge_graph
   ↓
5. 更新 documents 表 (status = 'completed')
   ↓
6. Vanna 自動訓練 (新增 Schema)
```

### Query Flow (查詢流程)

```
1. 用戶提問 (Web UI / API)
   「2023 年腾讯嘅營收係幾多？同去年比較點？」
   ↓
2. Nanobot Intent Router 分析
   ↓
3. Vanna 生成 SQL
   SELECT value FROM financial_metrics 
   WHERE company_id = 1 AND year = 2023 AND metric_name = 'revenue'
   ↓
4. PostgreSQL 執行查詢
   ↓
5. Nanobot 整合結果
   ├─ 財務數字 (2023: 609B, 2022: 554B, 增長 9.9%)
   ├─ 溯源信息 (source_page: 15, source_table_id: table_001)
   └─ 原始圖片 (SELECT file_path FROM raw_artifacts WHERE ...)
   ↓
6. 返回用戶 (数字 + 原始表格圖片)
```

---

## 🎯 CPU/GPU 分流策略

### 架構設計

```
┌─────────────────────────────────────────────┐
│          Docker Compose (統一配置)           │
├─────────────────────────────────────────────┤
│                                             │
│  .env 配置決定運行模式：                     │
│                                             │
│  CPU 用家:                    GPU 用家:      │
│  LLM_BACKEND=api             LLM_BACKEND=local
│  DASHSCOPE_API_KEY=xxx       VLLM_PORT=5000 │
│                              USE_CUDA=true  │
│                                             │
│  → 調用 API                   → 使用本地 GPU │
│     (唔使 GPU)                     (食滿 RTX) │
│                                             │
└─────────────────────────────────────────────┘
```

### Dockerfile 設計

```dockerfile
# 安裝 PyTorch (CUDA 版本)
RUN pip install torch --index-url https://download.pytorch.org/whl/cu118

# PyTorch 會自動檢測 GPU
# - 如果有 GPU → 使用 CUDA
# - 如果冇 GPU → 自動 fallback 到 CPU
# 唔會 Crash!
```

### Compose Profiles

```yaml
# GPU 用家額外啟動:
# docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up

# gpu.yml:
services:
  nanobot-gateway:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia  # GPU 用家先有
              count: all
              capabilities: [gpu]
```

---

## 📊 性能優化策略

### 1. 並行處理

```python
# Batch Processor 配置
MAX_CONCURRENT_TASKS=10  # 並行處理 10 個 PDF
BATCH_SIZE=20           # 每批 20 個
```

### 2. 批量插入

```python
# ❌ 慢 (逐條插入)
for record in records:
    await conn.execute("INSERT INTO ...", record)

# ✅ 快 (批量插入)
await conn.executemany(
    "INSERT INTO financial_metrics (...) VALUES (...)",
    records
)
# 速度快 10-50x
```

### 3. 索引優化

```sql
-- 必須有的索引
CREATE INDEX idx_metric_lookup 
ON financial_metrics(company_id, year, metric_name);

-- JSONB 索引
CREATE INDEX idx_kg_attributes 
ON knowledge_graph USING gin (attributes);

-- Vector 索引 (如果用 Hybrid Search)
CREATE INDEX idx_chunks_embedding 
ON document_chunks USING ivfflat (embedding vector_cosine_ops);
```

### 4. 連接池

```python
# asyncpg 連接池
pool = await asyncpg.create_pool(
    DATABASE_URL,
    min_size=5,
    max_size=20
)
```

---

## 🔒 安全性設計

### 1. 數據庫訪問控制

```sql
-- 只允许 nanobot-gateway 訪問
GRANT SELECT, INSERT, UPDATE ON financial_metrics TO nanobot_user;
GRANT SELECT ON knowledge_graph TO nanobot_user;
-- 不允許 DELETE (除非管理員)
```

### 2. 文件存儲隔離

```
Docker Volume 掛載:
- /app/data/raw → 僅 ingestion-worker 可寫
- /data/pdfs → 只讀掛載到 webui
```

### 3. API 限流

```python
# Nanobot Gateway 配置
RATE_LIMIT:
  requests_per_minute: 60
  burst: 10
```

---

## 📈 擴展性規劃

### Phase 1 (已完成): 單一公司 PoC
- ✅ PostgreSQL Schema
- ✅ OpenDataLoader 集成
- ✅ Vanna Text-to-SQL
- ✅ 基本 Web UI

### Phase 2 (下一步): 多公司支持
- [ ] 批量導入 100+ 公司年報
- [ ] 跨公司比較功能
- [ ] 財務指標標準化 (不同公司可能有不同命名)

### Phase 3 (未來): 實時更新
- [ ] HKEX 公告監控 (自動抓取新財報)
- [ ] 自動增量更新
- [ ] 異動通知

### Phase 4 (進階): AI 增強
- [ ] 異常檢測 (自動標注異常財務數據)
- [ ] 趨勢預測 (基於歷史數據)
- [ ] 自然語言報告生成

---

## 🎓 技術選型理由

| 組件 | 選型 | 理由 |
|------|------|------|
| 數據庫 | PostgreSQL 16 | JSONB + pgvector + ACID |
| PDF 解析 | OpenDataLoader | 開源、支持表格/圖片提取 |
| Text-to-SQL | Vanna | 專門為 SQL 生成優化、支持訓練 |
| Agent 框架 | Nanobot | 已有基礎、支持 Cantonese |
| 部署 | Docker Compose | 簡單、統一環境 |
| LLM | Qwen 2.5 | 中英粵三語、性價比高 |

---

## 📝 待辦事項清單

### 高優先級
- [ ] 完成 OpenDataLoader 實際集成 (而家係 Mock)
- [ ] 測試 Vanna 訓練流程
- [ ] 完善 Web UI (展示原始圖片)
- [ ] 添加錯誤處理和重試機制

### 中優先級
- [ ] 實現財務指標自動提取 (Qwen-VL)
- [ ] 添加數據驗證流程 (人工審核)
- [ ] 優化批量處理性能

### 低優先級
- [ ] 添加 Vector Search (pgvector)
- [ ] 實現跨公司比較
- [ ] 添加導出功能 (Excel/PDF)

---

**最後更新**: 2026-03-30  
**版本**: 1.0.0  
**維護者**: SFC AI Team
