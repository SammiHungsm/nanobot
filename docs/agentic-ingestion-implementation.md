# 🚀 Agentic Dynamic Ingestion 實現總結

**版本**: 1.0  
**日期**: 2026-04-10  
**狀態**: ✅ 已完成核心實現

---

## 📋 實現清單

| # | 項目 | 文件 | 狀態 |
|---|------|------|------|
| 1 | 數據庫 Schema | `storage/init_complete.sql` | ✅ |
| 2 | Ingestion Tools | `nanobot/agent/tools/db_ingestion_tools.py` | ✅ |
| 3 | Agentic Pipeline | `nanobot/ingestion/agentic_ingestion.py` | ✅ |
| 4 | Pipeline 整合 | `nanobot/ingestion/pipeline.py` | ✅ |

---

## 🏗️ 架構概覽

```
┌─────────────────────────────────────────────────────────────────┐
│                     PDF Upload                                   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│           Stage 0: Agentic Dynamic Ingestion (NEW)              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. Extract First 1-2 Pages                               │   │
│  │ 2. Agent Analysis (Entity Extraction)                    │   │
│  │    - Parent Company (or NULL for index reports)          │   │
│  │    - Subsidiaries / Index Constituents                   │   │
│  │    - Industries (AI extracted)                           │   │
│  │    - Dynamic Attributes → JSONB                          │   │
│  │ 3. Smart Insert (Entity + JSONB)                         │   │
│  │ 4. Create Review Record (if low confidence)              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│           Stage 1: Page Classification                          │
│  - LLM 語義分類 (找出財報相關頁面)                               │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│           Stage 2: Data Extraction                              │
│  - OpenDataLoader Parser (表格、文字、邊界框)                    │
│  - Financial Agent (結構化提取)                                 │
│  - Validator (數學規則驗證)                                     │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│           Database Storage                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ documents                                                │   │
│  │ - id, filename, parent_company_name                      │   │
│  │ - confirmed_industry (人工確認)                          │   │
│  │ - ai_extracted_industries (JSONB)                        │   │
│  │ - dynamic_attributes (JSONB) 🌟                          │   │
│  │ - zone1_raw_data (JSONB)                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ document_companies                                       │   │
│  │ - document_id, company_name, stock_code                  │   │
│  │ - relation_type (parent/subsidiary/constituent)          │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ data_review_queue                                        │   │
│  │ - review_type, ai_suggestions, status                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 新增 Tools

### 1. `get_db_schema`
```python
# 用途：讓 Agent 獲取當前資料庫 Schema
result = await agent.tools.execute("get_db_schema", {})
```

返回：
```json
{
  "schema": {
    "documents": [
      {"name": "id", "type": "uuid"},
      {"name": "parent_company_name", "type": "varchar"},
      {"name": "dynamic_attributes", "type": "jsonb"}
    ]
  },
  "design_notes": {
    "jsonb_columns": ["zone1_raw_data", "dynamic_attributes"]
  }
}
```

### 2. `smart_insert_document`
```python
# 用途：智能寫入文檔數據（實體欄位 + JSONB）
result = await agent.tools.execute("smart_insert_document", {
    "filename": "Annual_Report_2024.pdf",
    "file_path": "/data/uploads/report.pdf",
    "parent_company": "CK Hutchison Holdings",
    "parent_stock_code": "00001",
    "ai_industries": ["Finance", "Retail"],
    "subsidiaries": [
        {"name": "A.S. Watson", "stock_code": None, "relation_type": "subsidiary"}
    ],
    "dynamic_attributes": {
        "auditor": "KPMG",
        "reporting_currency": "HKD"
    },
    "confidence_scores": {
        "parent_company": 0.95,
        "industries": 0.85
    }
})
```

### 3. `update_dynamic_attributes`
```python
# 用途：更新 JSONB 動態屬性
result = await agent.tools.execute("update_dynamic_attributes", {
    "document_id": "uuid-here",
    "attributes": {
        "index_quarter": "Q3",
        "special_notes": "包含特殊事項"
    },
    "merge_mode": "merge"
})
```

### 4. `create_review_record`
```python
# 用途：創建待覆核記錄
result = await agent.tools.execute("create_review_record", {
    "document_id": "uuid-here",
    "review_type": "industry_confirmation",
    "ai_suggestions": {
        "ai_industries": ["Finance", "Technology"]
    },
    "confidence_score": 0.75,
    "priority": "normal"
})
```

---

## 📊 數據庫 Schema 設計

### 核心表：`documents`

```sql
CREATE TABLE documents (
    -- 實體欄位 (快速查詢)
    id UUID PRIMARY KEY,
    filename VARCHAR(500),
    parent_company_name VARCHAR(255),      -- 可為 NULL (恒指報告)
    confirmed_industry VARCHAR(255),       -- 人工確認
    document_type VARCHAR(100),
    fiscal_year INTEGER,
    
    -- 🌟 JSONB 動態欄位
    ai_extracted_industries JSONB,         -- AI 提取的多個行業
    zone1_raw_data JSONB,                  -- 原始提取數據
    dynamic_attributes JSONB,              -- 其他動態屬性
    
    -- 索引優化
    -- CREATE INDEX idx_documents_dynamic_attributes ON documents USING GIN(dynamic_attributes);
);
```

### 關聯表：`document_companies`

```sql
CREATE TABLE document_companies (
    id UUID PRIMARY KEY,
    document_id UUID REFERENCES documents(id),
    company_name VARCHAR(255),
    stock_code VARCHAR(20),
    relation_type VARCHAR(50),  -- 'parent', 'subsidiary', 'index_constituent'
);
```

### 覆核表：`data_review_queue`

```sql
CREATE TABLE data_review_queue (
    id UUID PRIMARY KEY,
    document_id UUID,
    review_type VARCHAR(50),
    status VARCHAR(20) DEFAULT 'pending',
    ai_suggestions JSONB,
    ai_confidence_score DECIMAL(3,2),
    human_feedback TEXT
);
```

---

## 🔧 使用方式

### 方式 1：直接調用 Pipeline

```python
from nanobot.ingestion.pipeline import DocumentPipeline

pipeline = DocumentPipeline(enable_agentic_ingestion=True)
await pipeline.connect()

# Stage 0: Agentic Ingestion
result = await pipeline.run_agentic_ingestion(
    pdf_path="/data/report.pdf",
    filename="Annual Report 2024.pdf",
    task_id="task-uuid"
)

# 繼續 Stage 1 & 2...
result = await pipeline.process_pdf(
    pdf_path="/data/report.pdf",
    doc_id=result["document_id"]
)

await pipeline.close()
```

### 方式 2：獨立使用 Agentic Pipeline

```python
from nanobot.ingestion.agentic_ingestion import run_agentic_ingestion

result = await run_agentic_ingestion(
    pdf_path="/data/report.pdf",
    filename="Annual Report 2024.pdf"
)

print(f"Document ID: {result['document_id']}")
print(f"Parent Company: {result['analysis']['parent_company']}")
print(f"Industries: {result['analysis']['industries']}")
```

### 方式 3：通過 Agent Loop

```python
from nanobot.agent.loop import AgentLoop

# Agent 會自動調用 smart_insert_document Tool
response = await agent_loop.process_direct(
    content="""
    請分析以下 PDF 文檔並寫入數據庫：
    文件：/data/report.pdf
    
    請提取公司信息、行業、並使用 smart_insert_document 工具寫入。
    """,
    session_key="ingestion:task"
)
```

---

## 🎯 設計決策

### 為什麼使用 JSONB？

| 場景 | 傳統方案 | JSONB 方案 |
|------|----------|------------|
| 新增欄位 | ALTER TABLE | 直接寫入 JSONB |
| 不同格式財報 | 需要預定義所有欄位 | 靈活存儲不同屬性 |
| 查詢性能 | 快 (索引) | 中等 (GIN 索引) |
| Schema 維護 | 複雜 | 簡單 |

### 為什麼保留 `confirmed_industry`？

```
AI 提取 → ai_extracted_industries (JSONB)
                      ↓
              人工覆核確認
                      ↓
       confirmed_industry (實體欄位) ← Vanna 查詢使用
```

這樣的雙軌設計確保：
- **靈活性**：AI 可以提取多個可能的行業
- **準確性**：最終查詢使用人工確認的值

---

## ✅ 測試檢查清單

### 單元測試
- [ ] `GetDBSchemaTool` 返回正確的 Schema
- [ ] `SmartInsertDocumentTool` 正確處理 NULL parent_company
- [ ] `UpdateDynamicAttributesTool` 正確合併 JSONB
- [ ] `CreateReviewRecordTool` 創建正確的覆核記錄

### 集成測試
- [ ] 完整流程：上傳 PDF → Stage 0 → Stage 1 → Stage 2
- [ ] 恒指報告：parent_company = NULL, 多個 constituents
- [ ] 年報：正常 parent_company, subsidiaries
- [ ] 低置信度：自動創建覆核記錄

### E2E 測試
- [ ] WebUI 上傳 → 查看數據庫結果
- [ ] 查詢 Vanna → 確認數據可用

---

## 📈 性能指標

| 指標 | 目標值 | 測量方法 |
|------|--------|----------|
| Stage 0 處理時間 | < 10s | 日誌分析 |
| AI 提取準確率 | > 85% | 人工抽樣 |
| 覆核率 | < 20% | 覆核隊列大小 |
| JSONB 查詢延遲 | < 100ms | EXPLAIN ANALYZE |

---

## 🔗 相關文檔

- [Database Schema](./init_complete.sql)
- [PDF Workflow Complete](./pdf-workflow-complete.md)
- [Code Fixes Summary](./code-fixes-summary.md)

---

## 📝 後續優化

### 短期 (1 週)
1. 添加前端覆核界面
2. 優化 AI 提示詞
3. 添加更多測試

### 中期 (1 個月)
1. 實現混合 RAG (SQL + Vector)
2. 添加 PDF 溯源高亮
3. 實現 Vanna 自動重訓

### 長期 (3 個月)
1. 支持更多文件格式
2. 添加多語言支持
3. 實現增量更新

---

**實現完成時間**: 2026-04-10  
**實現者**: AI Assistant  
**審核狀態**: 待審核