# Nanobot: 完整架構實現指南

## ✅ 已完成更新列表

### 1. Database Schema (`storage/init_complete.sql`)
**狀態: ✅ 完成**

已在 `documents` 和 `document_companies` 表添加：
- `index_theme`, `is_index_report`, `confirmed_industry` 欄位
- `dynamic_attributes`, `ai_extracted_industries` JSONB 欄位
- GIN 索引優化 JSONB 查詢效能

### 2. Vanna Training Data (`vanna/vanna_backend/training_data.py`)
**狀態: ✅ 更新完成**

新增內容：
- **DDL Statements**: 完整的 PostgreSQL 表定義（含 JSONB）
- **Documentation**: JSONB 查詢語法指南、行業分配規則說明
- **Question-SQL Pairs**: 20+ 個 JSONB 查詢範例
- **DDL Whitelist**: documents, document_companies 等白名單表

關鍵範例：
```sql
-- JSONB 查詢範例
SELECT dynamic_attributes->>'index_quarter' FROM documents WHERE dynamic_attributes->>'index_quarter' = 'Q3';

-- 檢查 Key 是否存在
SELECT * FROM documents WHERE dynamic_attributes ? 'key_name';

-- 查詢 JSON 數組
SELECT * FROM documents WHERE ai_extracted_industries ? 'Biotech';
```

### 3. Vanna Tool (`nanobot/agent/tools/vanna_tool.py`)
**狀態: ✅ 更新完成**

新增方法：
- `discover_dynamic_keys()`: 掃描資料庫中的所有 JSONB Keys
- `build_enhanced_prompt()`: 構建帶有動態 Schema 的 Prompt
- `generate_sql_with_dynamic_schema()`: Just-in-Time Schema Injection
- `query_with_dynamic_schema()`: 完整查詢 Pipeline

### 4. Dynamic Schema Tools (`nanobot/agent/tools/dynamic_schema_tools.py`)
**狀態: ✅ 新增**

Tools 列表：
- `GetDynamicKeysTool`: 發現所有 JSONB 動態 Keys
- `GetJSONBSchemaTool`: 完整 JSONB Schema 分析
- `PrepareVannaPromptTool`: 構建增強 Prompt

### 5. Ingestion Tools (`nanobot/agent/tools/db_ingestion_tools.py`)
**狀態: ✅ 完成**

Tools 列表：
- `SmartInsertDocumentTool`: 智能文檔寫入（支援規則 A/B）
- `UpdateDocumentStatusTool`: 更新處理狀態

### 6. Ingestion Skill (`nanobot/skills/ingestion_skill.py`)
**狀態: ✅ 新增**

Skill 包含：
- System Prompt: 行業分配規則完整說明
- Context: 資料庫 Schema 信息
- Tools: smart_insert_document, update_document_status
- 简化版分析邏輯（當 Agent Loop 不可用時）

### 7. Tools Registry (`nanobot/agent/tools/register_all.py`)
**狀態: ✅ 新增**

統一註冊函數：
```python
from nanobot.agent.tools.register_all import register_all_tools, get_default_registry

# 使用方式
registry = get_default_registry()
# 或
register_all_tools(existing_registry)
```

---

## 🔄 完整工作流程

### Phase 1: Agentic Ingestion (PDF 上傳)

```
1. WebUI 接收 PDF → POST /api/documents/upload
2. 提取前 1-2 頁 → first_pages_content
3. 加載 Ingestion Skill → agent.load_skill("ingestion")
4. Agent 分析內容:
   - 判斷報告類型 (annual_report / index_report)
   - 應用規則 A/B
   - 提取成分股
5. 呼叫 smart_insert_document Tool
6. 寫入 documents + document_companies
```

### Phase 2: Vanna 查詢 (自然語言 → SQL)

```
1. 用戶提問 → "Find all Q3 biotech reports"
2. 呼叫 get_dynamic_keys Tool:
   - 發現: ['index_quarter', 'report_version', 'is_audited']
3. 構建增強 Prompt:
   - 用戶問題 + JSONB Keys + 查詢語法提示
4. Vanna 生成 SQL:
   - SELECT * FROM documents WHERE dynamic_attributes->>'index_quarter' = 'Q3'
5. 執行查詢 → 返回結果
```

---

## 📁 文件結構

```
nanobot/
├── agent/
│   └── tools/
│       ├── __init__.py               # 基礎導出
│       ├── register_all.py           # 統一註冊 (新增)
│       ├── db_ingestion_tools.py     # 智能寫入 Tools
│       ├── dynamic_schema_tools.py   # JSONB Tools (新增)
│       ├── vanna_tool.py             # Vanna + Schema Injection (更新)
│       └── registry.py               # Tool Registry
│
├── skills/
│   └── ingestion_skill.py            # Ingestion Skill (新增)
│
└── ingestion/
    └── two_phase_pipeline.py         # Two-Phase Pipeline
    └── agentic_ingestion.py          # Agent System Prompt

vanna/
└── vanna_backend/
    └── training_data.py              # Vanna 訓練數據 (更新)
    └── vanna_config.py               # Vanna 配置

storage/
└── init_complete.sql                 # 資料庫 Schema
```

---

## 🚀 使用指南

### 啟動服務

```bash
# 1. 啟動 PostgreSQL
docker-compose up -d postgres

# 2. 初始化資料庫
psql -U postgres -d annual_reports -f storage/init_complete.sql

# 3. 啟動 WebUI
cd nanobot
python -m uvicorn webui.app.main:app --host 0.0.0.0 --port 8080 --reload

# 4. 訓練 Vanna
python -c "
from nanobot.agent.tools.vanna_tool import VannaSQL
vanna = VannaSQL()
vanna.train_schema()
"
```

### 使用 Tools

```python
# 獲取預配置 Registry
from nanobot.agent.tools.register_all import get_default_registry

registry = get_default_registry()
print(registry.tool_names)

# 使用 SmartInsertDocumentTool
result = await registry.execute(
    "smart_insert_document",
    {
        "filename": "hsi_biotech_q3.pdf",
        "report_type": "index_report",
        "index_theme": "Hang Seng Biotech Index",
        "confirmed_doc_industry": "Biotech",
        "industry_assignment_rule": "A",
        "sub_companies": [
            {"name": "Sino Biopharmaceutical", "stock_code": "1177.HK"},
            {"name": "WuXi Biologics", "stock_code": "2269.HK"}
        ]
    }
)

# 使用 GetDynamicKeysTool
keys = await registry.execute("get_dynamic_keys", {})
print(keys)  # ['index_quarter', 'report_version', ...]
```

### 使用 Vanna with Schema Injection

```python
from nanobot.agent.tools.vanna_tool import VannaSQL

vanna = VannaSQL()

# 標準查詢
result = vanna.query("Show all index reports")

# 帶動態 Schema 的查詢 (推薦)
result = await vanna.query_with_dynamic_schema("Find Q3 biotech reports")
print(result['dynamic_keys_discovered'])  # ['index_quarter', 'is_audited']
```

### 使用 Ingestion Skill

```python
from nanobot.skills.ingestion_skill import IngestionSkill
from nanobot.agent.loop import AgentLoop

# 初始化
agent = AgentLoop()
skill = IngestionSkill()
skill.load(agent)

# 执行
pdf_content = extract_first_pages("report.pdf")
result = await skill.execute("report.pdf", pdf_content)
print(result)
```

---

## ⚠️ 重要提醒

### 行業分配規則

| 規則 | 適用場景 | 行業來源 | industry_source |
|------|----------|----------|-----------------|
| A | 指數報告 | confirmed_industry (強制) | 'confirmed' |
| B | 年報 | ai_extracted_industries | 'ai_extracted' |

### JSONB 查詢語法

```sql
-- ✅ 正確: 使用 ->> 提取 text
SELECT dynamic_attributes->>'key' FROM documents;

-- ❌ 錯誤: 直接用 key (不存在此欄位)
SELECT key FROM documents;
```

### Vanna 必須知道 JSONB Keys

- **問題**: Vanna 預設看不到 JSONB 中的屬性
- **解法**: 查詢前先呼叫 `get_dynamic_keys` Tool
- **效果**: Vanna 生成正確的 JSONB 查詢語法

---

## 📊 測試檢查清單

1. ✅ 資料庫 Schema 初始化成功
2. ✅ Vanna 訓練數據更新完成
3. ⬜ WebUI 上傳 PDF 測試
4. ⬜ Ingestion Skill 測試
5. ⬜ Vanna JSONB 查詢測試
6. ⬜ 規則 A/B 行業分配測試

---

## 📝 下一步

1. **啟動 Docker 環境**: `docker-compose up -d`
2. **測試 WebUI 上傳**: 上傳一份指數報告 PDF
3. **驗證行業分配**: 檢查 document_companies 表
4. **測試 Vanna 查詢**: 查詢動態屬性
5. **Debug Log**: 添加更多日誌以便追蹤問題