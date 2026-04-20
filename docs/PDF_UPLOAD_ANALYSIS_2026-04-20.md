# PDF 上傳流程分析報告

## 測試時間
2026-04-20 09:27 (Asia/Hong_Kong)

## 測試文件
- `stock_00001_2023.pdf` (已存在於數據庫，ID: 6)
- `3SBIO.pdf` (已存在於數據庫，ID: 5)

---

## 1. 數據庫當前狀態

### 有數據的表
| 表名 | 數據量 | 說明 |
|------|--------|------|
| documents | 2 rows | PDF 文檔記錄 |
| document_pages | 225 rows | 頁面內容（來自 3SBIO.pdf） |
| companies | 1 row | 3SBIO INC. (01530) |
| document_companies | 1 row | 文檔-公司關聯 |
| document_summary | 2 rows | 文檔摘要 |
| document_processing_history | 4 rows | 處理歷史 |

### 空表（13 個）
| 表名 | 預期數據來源 |
|------|-------------|
| financial_metrics | Stage 4 結構化提取 |
| revenue_breakdown | Stage 4 結構化提取 |
| key_personnel | Stage 4 結構化提取 |
| shareholding_structure | Stage 4 結構化提取 |
| document_chunks | Stage 7 向量索引 |
| document_tables | Stage 2 表格保存 |
| raw_artifacts | Stage 2 原始 artifacts |
| entity_relations | Stage 2 實體關係 |
| market_data | 外部數據 |
| review_queue | 審核佇列 |
| artifact_relations | Artifact 關聯 |
| vanna_training_data | Vanna 訓練數據 |
| v_tables_with_context_for_vanna | Vanna 視圖 |

---

## 2. 問題分析

### 根本原因：Stage 2 的表格處理有 Bug

#### 發現的問題

1. **表格格式問題**：
   - LlamaParse 返回的表格是 **HTML 格式**（`<table>...</table>`）
   - 不是 Markdown 格式（`| col1 | col2 |`）
   - 例如 Page 7 的 Financial Highlights 表格：
   ```html
   <table>
     <thead><tr><th> </th><th>2020</th><th>2021</th>...</tr></thead>
     <tbody>
       <tr><td>Revenue</td><td>5,587,636</td>...</tr>
     </tbody>
   </table>
   ```

2. **Stage 2 沒有正確處理 HTML 表格**：
   - `has_tables = False`（所有 225 頁都是 False）
   - `metadata = {}`（空的 JSON）
   - Stage 2 的 `_is_messy_table()` 方法只檢測 Markdown 表格格式
   - HTML 表格沒有被識別為表格

3. **Stage 4 結構化提取沒有執行**：
   - 因為 `has_tables = False`
   - Stage 3 Router 不會路由到相關頁面
   - Stage 4 Extractor 沒有表格數據可提取
   - 導致 `financial_metrics`, `revenue_breakdown` 等表都是空的

#### 流程中斷點

```
Stage 0 (Preprocessor): ✅ 完成（Vision 提取封面）
Stage 0.5 (Registrar): ✅ 完成（文檔註冊）
Stage 1 (Parser): ✅ 完成（LlamaParse 解析，225 頁）
Stage 2 (Enrichment): ⚠️ 部分完成
   - ✅ 頁面內容已保存（document_pages）
   - ❌ 表格沒有被識別（has_tables = False）
   - ❌ metadata 沒有填充（metadata = {}）
Stage 3 (Router): ❌ 沒有執行（沒有表格頁面可路由）
Stage 4 (Extractor): ❌ 沒有執行（沒有目標頁面）
Stage 5-8: ❌ 都沒有執行
```

---

## 3. Bug 詳細分析

### Bug 位置：`nanobot/ingestion/stages/stage2_enrichment.py`

#### 問題 1：表格檢測邏輯錯誤

```python
@staticmethod
def _is_messy_table(md_content: str) -> bool:
    """
    防禦性檢查：判斷 Markdown 表格是否解析失敗
    """
    # ❌ 只檢查 Markdown 格式
    # 沒有處理 HTML 表格格式
    if "|" in md_content and "---" not in md_content:
        return True
```

這個方法假設表格是 Markdown 格式（`|` 和 `---`），但 LlamaParse 返回的是 HTML 格式。

#### 問題 2：Artifacts 處理邏輯

```python
# Stage 2 遍歷 artifacts
for artifact in artifacts:
    art_type = artifact.get("type")
    
    # 處理 Table
    if art_type == "table":
        # ❌ 這裡沒有被執行，因為 artifacts 中沒有 type="table" 的元素
        # LlamaParse 把表格內嵌在 markdown 中，不是獨立的 artifact
```

#### 問題 3：`has_tables` 設置邏輯

```python
# 預先掃描：找出含有圖片和表格的頁碼
pages_with_tables = set()
for a in artifacts:
    if a is not None:
        a_type = a.get("type")
        if a_type == "table":
            pages_with_tables.add(p_num)  # ❌ 永遠不會執行
```

---

## 4. 修復建議

### 方案 A：修改 Stage 2 檢測 HTML 表格

在 `save_all_artifacts` 中添加 HTML 表格檢測：

```python
# 檢查 markdown_content 是否包含 HTML 表格
if "<table" in content.lower() and "</table>" in content.lower():
    has_tables_flag = True
    # 解析 HTML 表格並存入 metadata
```

### 方案 B：在 Stage 1 解析 HTML 表格

在 `_extract_result` 中將 HTML 表格轉換為結構化數據：

```python
# 檢測並解析 HTML 表格
from bs4 import BeautifulSoup
soup = BeautifulSoup(markdown_content, 'html.parser')
tables = soup.find_all('table')
for table in tables:
    # 轉換為結構化格式
```

### 方案 C：在 Stage 4 直接從 markdown 提取

修改 Stage 4 Agentic Extractor，直接從 markdown 中提取表格：

```python
# 檢測 markdown 中的 HTML 表格
# 使用 LLM 從 HTML 表格中提取結構化數據
```

---

## 5. 總結

### 問題根因
**Stage 2 (Enrichment) 沒有正確處理 LlamaParse 返回的 HTML 格式表格**

### 影響範圍
1. `has_tables` 標誌沒有設置
2. `metadata` 沒有填充表格數據
3. Stage 3 Router 沒有目標頁面
4. Stage 4 Extractor 沒有執行
5. 所有結構化表都是空的

### 這是 Bug 嗎？
**是的，這是一個 Bug**

原因：
1. 代碼假設表格是 Markdown 格式
2. 但 LlamaParse 返回的是 HTML 格式
3. 沒有對 HTML 表格進行處理

### 修復優先級
**高優先級**

因為這個 Bug 導致整個 Pipeline 無法正常工作，無法從 PDF 中提取結構化數據。

---

## 6. 建議下一步

1. **立即修復** Stage 2 的 HTML 表格檢測邏輯
2. **重新運行** Pipeline 處理現有 PDF
3. **驗證** 表格數據是否正確插入到 `financial_metrics` 等表
4. **添加測試** 確保 HTML 表格被正確處理
