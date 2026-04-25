---
name: semantic-search
description: 當用戶問題涉及「策略」、「解釋」、「展望」、「評論」等非結構化內容時，使用 semantic_search 工具進行語意搜索。
metadata: {"nanobot":{"emoji":"🔍"}}
---

# Semantic Search Skill

## When to use

當用戶問題涉及**非結構化內容**，例如：

- 管理層對業務表現的**解釋**或**評論**
- 公司**策略方向**或**發展規劃**
- **未來展望**或**風險因素**描述
- 主席或CEO**年報致辭**的具體內容
- 任何需要「引述原文」才能回答的問題

## Tool: semantic_search

```python
semantic_search(query="管理層點解釋盈利下跌", year=2023, limit=5)
```

### 參數說明

| 參數 | 必填 | 說明 |
|------|------|------|
| query | ✅ | 自然語言搜索查詢 |
| company_name | ❌ | 公司名過濾（中英文皆可）|
| year | ❌ | 年份過濾 |
| limit | ❌ | 返回結果數量（默認 5）|

## 工具選擇规则

| 問題類型 | 使用工具 |
|---------|---------|
| 具體數字（營收、利潤、股價）| `direct_sql` |
| 持股量、公司關係 | `direct_sql` |
| 策略、解釋、評論、展望 | **`semantic_search`** |
| 需要原始表格或圖表 | `get_document_content` |

## 示例

**問：管理層點解釋2023年盈利下跌？**

```python
semantic_search(query="management explanation for profit decline", year=2023)
```

**問：公司對AI發展嘅策略係咩？**

```python
semantic_search(query="AI development strategy future outlook", limit=5)
```

**問：主席喺年報入面點評未來展望？**

```python
semantic_search(query="chairman outlook future outlook remarks", limit=5)
```

## 輸出格式

`semantic_search` 返回：
1. 與查詢相關的文檔切片列表
2. 每個切片的相似度分數
3. 切片內容預覽

然後可以使用 `get_document_content` 讀取完整內容。

## 限制

- `semantic_search` 需要 `document_chunks` 表有 `embedding_vector` 欄位
- 如果 Vector Search 返回空結果，嘗試擴大 `limit` 或改變 query 用詞
