# Nanobot 修復完成報告

**日期:** 2026-03-30  
**修復範圍:** Vanna、OpenDataLoader、RagAnything 整合  

---

## ✅ 測試結果

所有 5 個測試已通過：

```
[PASS] Vanna SQL Safety
[PASS] OpenDataLoader Integration
[PASS] MongoDB Semantic Search
[PASS] SKILL.md Intent Routing
[PASS] build_indexes.py Integration

Total: 5 passed / 0 skipped / 0 failed / 5 total
```

---

## 🔧 修復摘要

### 1. Vanna SQL 執行安全性

**問題:** Vanna 直接執行 SQL，冇經過 `financial_storage.py` 嘅參數化查詢，有 SQL 注入風險。

**修復:**
- 更新 `nanobot/agent/tools/vanna_tool.py` 嘅 `execute()` 方法
- 改用 `PostgresStorage` 執行 SQL
- 確保所有查詢都經過 SQLAlchemy 嘅安全處理

**驗證:**
```python
from nanobot.agent.tools.vanna_tool import VannaSQL

vanna = VannaSQL()
result = vanna.query("Show Tencent's revenue for 2020-2023")
# 而家會自動經過 PostgresStorage 嘅安全查詢
```

---

### 2. OpenDataLoader 整合

**問題:** `build_indexes.py` 只係用 PyMuPDF，未整合 OpenDataLoader 解析複雜表格。

**修復:**
- 喺 `nanobot/skills/document_indexer/scripts/build_indexes.py` 加入：
  - `call_opendataloader()` 函數：調用 OpenDataLoader CLI
  - `extract_tables_with_pymupdf()` 函數：PyMuPDF 後備方案
  - 自動判斷：如果 PDF 超過 50 頁，自動使用 OpenDataLoader
  - 輸出 `tables.json` 儲存所有提取嘅表格

**用法:**
```bash
# 一般 PDF (少過 50 頁) - 用 PyMuPDF
uv run python nanobot/skills/document_indexer/scripts/build_indexes.py "report.pdf"

# 複雜 PDF (超過 50 頁) - 自動用 OpenDataLoader
uv run python nanobot/skills/document_indexer/scripts/build_indexes.py "annual_report_200pages.pdf"
```

**輸出結構:**
```
workspace/indexes/<doc_name>/
├── toc.md              # PDF 目錄
├── metadata.md         # 封面元數據
├── navigation_context.md  # 前 5 頁內容
├── tables.json         # 提取嘅表格 (OpenDataLoader 或 PyMuPDF)
├── table_index.json    # 表格索引
└── status.txt          # 處理狀態
```

---

### 3. MongoDB 語義檢索

**問題:** `financial_storage.py` 只有 `$text search`，未支援語義檢索。

**修復:**
- 喺 `MongoDocumentStore` 類加入 `semantic_search()` 方法
- 支援兩種模式：
  1. **向量檢索** (`$vectorSearch`)：如果安裝咗 RagAnything 或 MongoDB Atlas
  2. **文本檢索** (`$text search`)：後備方案

**用法:**
```python
from nanobot.storage.financial_storage import MongoDocumentStore

store = MongoDocumentStore()
store.connect()

# 語義檢索
results = store.semantic_search(
    query="營收增長策略",
    company_name="Tencent",
    year=2023,
    limit=10
)

# 文本檢索 (舊方法)
results = store.search_text(
    query="營收增長",
    company_name="Tencent",
    year=2023,
    limit=10
)
```

**配置向量檢索 (選用):**
如果你有用 RagAnything 或 MongoDB Atlas，需要：
1. 安裝對應 SDK
2. 配置向量索引
3. 實現 `_get_embedding()` 方法

---

### 4. SKILL.md 意圖路由

**問題:** Agent 唔清楚幾時用邊個工具。

**修復:**
- 更新 `nanobot/skills/document_indexer/SKILL.md`
- 添加明確嘅工具選擇邏輯：

**工具選擇規則:**

| 問題類型 | 使用工具 | 示例 |
|---------|---------|------|
| **具體數字** (營收、利潤、增長率) | `vanna_tool` | "Show Tencent's revenue for 2020-2023" |
| **計算/排行** (平均值、前 10 大) | `vanna_tool` | "What are the top 5 companies by revenue?" |
| **跨年比較/趨勢** | `vanna_tool` | "Compare Alibaba's profit growth year-over-year" |
| **主觀描述/政策解釋** | 語義檢索 | "Explain the company's risk management strategy" |
| **業務描述/戰略分析** | 語義檢索 | "What are Tencent's main business segments?" |
| **精確頁碼引用** | 文檔索引 | "Show me the exact table on page 45" |

---

## 📋 下一步建議

### 1. 訓練 Vanna

```bash
# 訓練 Vanna 喺你嘅財務數據庫 Schema
uv run python train_vanna.py
```

### 2. 測試 PDF 索引建立

```bash
# 測試簡單 PDF
uv run python nanobot/skills/document_indexer/scripts/build_indexes.py "C:/path/to/report.pdf"

# 測試複雜 PDF (會自動用 OpenDataLoader)
uv run python nanobot/skills/document_indexer/scripts/build_indexes.py "C:/path/to/annual_report_200pages.pdf"
```

### 3. 配置 RagAnything (選用)

如果你想用语義檢索嘅向量模式：

```python
# 1. 安裝 RagAnything
uv pip install raganything

# 2. 配置 API Key
# 喺 .env 文件加入:
RAGANYTHING_API_KEY=your_api_key_here

# 3. 實現 _get_embedding() 方法
# 喺 financial_storage.py 嘅 MongoDocumentStore 類：
def _get_embedding(self, text: str) -> List[float]:
    from raganything import RagAnything
    rag = RagAnything(api_key=os.getenv('RAGANYTHING_API_KEY'))
    return rag.embed(text)
```

### 4. 測試意圖路由

創建一個測試腳本：

```python
from nanobot.agent.tools.vanna_tool import VannaSQL
from nanobot.storage.financial_storage import MongoDocumentStore

# 測試 Vanna (數字問題)
vanna = VannaSQL()
result = vanna.query("What are the top 5 companies by revenue in 2023?")
print(f"Vanna 結果：{result}")

# 測試語義檢索 (文本問題)
store = MongoDocumentStore()
store.connect()
results = store.semantic_search("管理層討論人工智能投資", limit=5)
print(f"語義檢索結果：{results}")
```

---

## 🎯 完整工作流程

```
用戶提問
   │
   ├─ 如果是數字問題 (營收、利潤、增長率)
   │     ↓
   │  Vanna Text-to-SQL
   │     ↓
   │  PostgreSQL 查詢
   │     ↓
   │  精確數字答案
   │
   ├─ 如果是文本問題 (策略、描述、解釋)
   │     ↓
   │  語義檢索 (RagAnything/MongoDB)
   │     ↓
   │  相關文本段落
   │     ↓
   │  LLM 總結答案
   │
   └─ 如果需要精確頁碼
         ↓
         文檔索引 (build_indexes.py)
         ↓
         索引文件 (toc.md, tables.json)
         ↓
         精確頁碼引用
```

---

## 📝 重要提醒

### 使用 .venv 環境

**所有腳本必須用 `uv run` 運行：**

```bash
# 正確 ✅
uv run python train_vanna.py
uv run python nanobot/skills/document_indexer/scripts/build_indexes.py "report.pdf"

# 錯誤 ❌
python train_vanna.py  # 可能用到系統 Python，缺少依賴
```

### Docker 部署

如果你用 Docker：

```bash
# 重建容器
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# 查看日誌
docker-compose logs -f nanobot-gateway
```

---

## 📊 性能優化建議

### 1. OpenDataLoader vs PyMuPDF

| 場景 | 建議工具 | 原因 |
|------|---------|------|
| PDF < 50 頁 | PyMuPDF | 快速、簡單 |
| PDF > 50 頁 | OpenDataLoader | 準確解析複雜表格 |
| 跨頁表格 | OpenDataLoader | 唯一支援 |
| 批量處理 | PyMuPDF | 速度快 10 倍 |

### 2. 向量檢索配置

如果你有大量文檔 (>1000 份)：
- 使用 MongoDB Atlas Vector Search
- 或者 PostgreSQL pgvector
- 避免全文檢索性能下降

### 3. Vanna 訓練

- 定期重新訓練 (每次 Schema 變更後)
- 加入更多示例查詢提高準確度
- 監控 SQL 生成失敗率

---

## 🔍 故障排除

### 問題 1: OpenDataLoader CLI 找不到

```bash
# 確認安裝
uv pip show opendataloader-pdf

# 如果未安裝
uv pip install opendataloader-pdf
```

### 問題 2: Vanna SQL 生成失敗

```python
# 檢查數據庫連接
from nanobot.storage.financial_storage import PostgresStorage
storage = PostgresStorage()
storage.connect()  # 應該冇錯誤

# 重新訓練 Vanna
uv run python train_vanna.py
```

### 問題 3: 語義檢索結果不準確

```python
# 檢查 MongoDB 連接
from nanobot.storage.financial_storage import MongoDocumentStore
store = MongoDocumentStore()
store.connect()

# 測試文本檢索
results = store.search_text("營收", limit=5)
print(results)

# 如果文本檢索都唔准，檢查 MongoDB 索引
# db.documents.createIndex({"content": "text"})
```

---

## ✅ 驗證清單

- [x] Vanna SQL 執行安全性修復
- [x] OpenDataLoader 整合到 build_indexes.py
- [x] MongoDB 語義檢索添加到 financial_storage.py
- [x] SKILL.md 意圖路由文檔更新
- [x] 所有測試通過 (5/5)
- [ ] (選用) 配置 RagAnything 向量檢索
- [ ] (選用) 加入更多 Vanna 示例查詢
- [ ] (選用) 設置 MongoDB 向量索引

---

**修復完成！** 🎉

所有核心功能已修復並測試通過。跟住「下一步建議」繼續配置就得！
