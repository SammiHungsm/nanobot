# Code Review Report - 2026-04-25

## Review 範圍

1. `vanna/` - Text-to-SQL 微服務
2. `storage/` - 資料庫 Schema
3. `nanobot/ingestion/` - PDF 處理 Pipeline

---

## 🔴 重大發現：文檔與代碼不一致

### 問題：Review 文檔引用不存在的檔案

| 文檔檔案 | 引用路徑 | 實際路徑 | 問題 |
|----------|----------|----------|------|
| `REVIEW_2026-04-24.md` | `vanna-service/start.py` (~1256行) | **不存在** | ❌ |
| `REVIEW_2026-04-24.md` | `vanna-service/vanna_training.py` (~700行) | **不存在** | ❌ |
| `VANNA_MICROSERVICE_REFACTOR.md` | `vanna-service/start.py` | **不存在** | ❌ |
| `README.md` | `vanna-service/start.py` (1256行) | **不存在** | ❌ |

### 實際 Vanna Backend 檔案結構

```
vanna/
├── README.md                          # 說明這是原型
├── docker-compose.yml
├── vanna_backend/
│   ├── app_alicloud_mysql.py          # ~391 行 - Flask 應用
│   ├── training_data.py               # ~461 行 - 訓練數據（DDL/Docs/SQL）
│   ├── utility.py                     # ~153 行 - 工具函數
│   ├── vanna_config.py                # ~18 行 - Vanna 配置
│   ├── test_chart.py                  # ~29 行 - 測試
│   ├── chroma_db/                     # ChromaDB 向量存儲
│   └── requirements.txt
```

**結論：Review 文檔聲稱「正確」但實際未檢查到真實檔案**

---

## 1. Vanna Service Review

### 檔案：`vanna/vanna_backend/app_alicloud_mysql.py` (~391 行)

| 區塊 | 狀態 | 說明 |
|------|------|------|
| 版本標註 | ⚠️ 無 | 沒有版本標註 |
| API Endpoints | ✅ 正確 | Flask routes 結構清晰 |
| Vanna 初始化 | ✅ 正確 | 使用 AliCloud + ChromaDB |
| MySQL 連接 | ✅ 正確 | 使用 mysql.connector |
| 錯誤處理 | ✅ 正確 | 有基本的 try-catch |
| 中文註解 | ✅ 正確 | 詳細說明用途 |

**品質評分：7/10**

---

### 檔案：`vanna/vanna_backend/training_data.py` (~461 行)

| 區塊 | 狀態 | 說明 |
|------|------|------|
| DDL 定義 | ❌ **過時** | **與 init_complete.sql 不一致** |
| Documentation | ✅ 正確 | JSONB 查詢說明正確 |
| SQL Examples | ⚠️ 部分過時 | 基於過時的 DDL |

#### ❌ DDL 不一致問題

| 欄位/表 | `training_data.py` DDL | `init_complete.sql` 實際 Schema | 問題 |
|---------|-------------------------|----------------------------------|------|
| `documents.index_theme` | ✅ 存在 | ❌ 不存在（用 `dynamic_attributes JSONB`） | **過時** |
| `documents.parent_company` | ✅ 存在 | ❌ 不存在 | **過時** |
| `documents.is_index_report` | ✅ 存在 | ❌ 不存在 | **過時** |
| `document_companies.assigned_industry` | ✅ 存在 | ❌ `extracted_industries JSONB` | **過時** |
| `document_companies.company_name` | ✅ 存在 | ❌ `company_id` FK | **過時** |
| `document_chunks.embedding` | `VECTOR(1536)` | `VECTOR(384)` | **維度錯誤** |
| `document_tables.table_name` | ✅ 存在 | ❌ `title` | **過時** |
| `key_personnel.board_role` | ✅ 存在 | ❌ 沒有 `board_role` 欄位 | **過時** |

**結論：DDL 訓練數據與實際 Schema 嚴重脫節，會導致 Vanna 生成的 SQL 失敗**

**品質評分：4/10**（需要立即更新 DDL）

---

### 檔案：`vanna/vanna_backend/utility.py` (~153 行)

| 函數 | 狀態 | 說明 |
|------|------|------|
| `reframe_user_query` | ✅ 正確 | 用戶名注入 |
| `refine_queries` | ✅ 正確 | LIKE 關鍵字模糊化 |
| `add_realnames` | ✅ 正確 | 別名替換 |
| `find_table_alias` | ✅ 正確 | SQL 解析 |
| `replace_columns` | ✅ 正確 | 欄位替換（脫敏） |
| `read_docx_file` | ✅ 正確 | Word 文檔讀取 |

**品質評分：9/10**

---

## 2. Storage (Database Schema) Review

### 檔案：`storage/init_complete.sql` (~1500 行)

| 表名 | 設計評估 | 註解準確性 |
|------|----------|------------|
| `companies` | ✅ 優秀 | ✅ 正確 |
| `documents` | ✅ 優秀 | ✅ 正確 |
| `document_companies` | ✅ 優秀 | ✅ 正確 |
| `document_processing_history` | ✅ 優秀 | ✅ 正確 |
| `document_pages` | ✅ 優秀 | ✅ 正確 |
| `document_chunks` | ✅ 優秀 | ✅ 正確（`VECTOR(384)`） |
| `document_tables` | ✅ 優秀 | ✅ 正確（`title` 欄位） |
| `review_queue` | ✅ 優秀 | ✅ 正確 |
| `vanna_training_data` | ✅ 優秀 | ✅ 正確 |
| `financial_metrics` | ✅ 優秀 | ✅ 正確 |
| `market_data` | ✅ 優秀 | ✅ 正確 |
| `revenue_breakdown` | ✅ 優秀 | ✅ 正確 |
| `key_personnel` | ✅ 優秀 | ✅ 正確 |
| `shareholding_structure` | ✅ 優秀 | ✅ 正確 |
| `raw_artifacts` | ✅ 優秀 | ✅ 正確 |
| `entity_relations` | ✅ 優秀 | ✅ 正確 |
| `artifact_relations` | ✅ 優秀 | ✅ 正確 |

**Schema 設計評分：10/10**

**Schema 文檔評分：10/10**

---

## 3. Ingestion Pipeline Review

### 檔案：`nanobot/ingestion/pipeline.py` (~580 行)

| 區塊 | 狀態 | 說明 |
|------|------|------|
| Pipeline 流程 | ✅ 正確 | Stage 1 先行設計正確 |
| 版本標註 | ✅ 正確 | v4.0, v4.3, v4.6, v4.7, v4.8 標註清晰 |
| 抽象方法 | ✅ 正確 | `extract_information` 委託給 Stage 4 |
| Stage 職責 | ✅ 正確 | 每個 Stage 職責清晰 |

**品質評分：9/10**

---

### 檔案：`nanobot/ingestion/base_pipeline.py` (~242 行)

| 區塊 | 狀態 | 說明 |
|------|------|------|
| 模板方法模式 | ✅ 正確 | 清晰描述 run() 骨架 |
| LlamaParse 整合 | ✅ 正確 | v3.2 標註 |
| 異步設計 | ✅ 正確 | async/await 正確使用 |

**品質評分：9/10**

---

## 4. 版本號一致性

| 位置 | 版本 | 狀態 |
|------|------|------|
| CHANGELOG.md | Pipeline v4.8.4 | ✅ 最新 |
| README.md | Pipeline v4.13 | ⚠️ 過時 |
| `pipeline.py` 註解 | v4.0 | ✅ 準確 |
| `init_complete.sql` | Schema v2.3 | ✅ 正確 |
| Vanna Service | v2.3.0（聲稱） | ❌ 無法驗證（檔案不存在） |

---

## 5. 總結

### 評分總覽

| 模組 | 評分 | 主要問題 |
|------|------|----------|
| vanna-service (實際) | 6/10 | DDL 過時，檔案路徑錯誤 |
| storage | 10/10 | 無問題 |
| ingestion | 9/10 | README 版本號過時 |

### ❌ 需要立即修復

1. **DDL 同步**：更新 `training_data.py` 的 DDL 以匹配 `init_complete.sql`
   - 移除不存在的欄位（`index_theme`, `parent_company`, `is_index_report`）
   - 更新 `document_companies` 結構（使用 `company_id` FK）
   - 修正 `document_chunks.embedding` 維度（`VECTOR(384)`）
   - 修正 `document_tables.table_name` → `title`

2. **文檔同步**：更新所有 Review 文檔
   - 修正 `vanna-service/start.py` → `vanna_backend/app_alicloud_mysql.py`
   - 修正 `vanna-service/vanna_training.py` → `vanna_backend/training_data.py`

3. **版本號更新**：更新 README.md 中的 Pipeline 版本至 v4.8.4

---

## 6. 行動項目

| 優先級 | 項目 | 負責檔案 |
|--------|------|----------|
| 🔴 高 | 更新 DDL 訓練數據 | `training_data.py` |
| 🔴 高 | 修正 Review 文檔路徑 | `REVIEW_2026-04-*.md`, `VANNA_MICROSERVICE_REFACTOR.md` |
| 🟡 中 | 更新 README 版本號 | `README.md` |
| 🟢 低 | 統一註解語言 | 全域 |
