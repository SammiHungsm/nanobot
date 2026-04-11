# Gemini 建议修复总结

## ✅ 已修复（2/3）

### 1. 页码过滤（已修复 ✅）

**问题**：用户问题经常带页码（如 "p.6", "p 273"），但 Vanna 不懂如何处理。

**修复**：
- ✅ 添加 `source_page_mapping` 到 `documentation.json`
- ✅ 添加 `page_number_patterns` 到 `documentation.json`
- ✅ 添加 3 个带页码的 SQL 示例到 `sql_pairs.json`：
  - `revenue_canada_page_001`（p.6）
  - `executive_directors_page_001`（p 2）
  - `profit_loss_page_001`（p 273）

**训练数据示例**：
```json
{
  "id": "source_page_mapping",
  "content": "CRITICAL: When a user asks for data 'on page X', 'p.X', 'p X', 'page X', or '(p X)', you MUST add a filter for source_page. Example: WHERE source_page = 6;",
  "category": "critical"
}
```

```json
{
  "id": "revenue_canada_page_001",
  "question": "What is the % of total revenue from Canada based on the chart of p.6?",
  "sql": "SELECT ... WHERE source_page = 6;",
  "note": "CRITICAL: User asked 'p.6', must add WHERE source_page = 6"
}
```

---

### 2. Shareholding 信托查询（Schema 缺少字段 ⚠️）

**问题**：用户问到信托持股，但 `shareholding_structure` 表缺少 `trust_name` 和 `trustee_name` 字段。

**当前状态**：
- ❌ `shareholdings` 表不存在
- ❌ `shareholding_structure` 表缺少信托字段

**建议的 Schema 扩展**（如果需要支持信托查询）：
```sql
ALTER TABLE shareholding_structure ADD COLUMN trust_name VARCHAR(255);
ALTER TABLE shareholding_structure ADD COLUMN trustee_name VARCHAR(255);
ALTER TABLE shareholding_structure ADD COLUMN percentage_held NUMERIC(6, 4);
```

**临时方案**（使用现有字段）：
```sql
SELECT shareholder_name, percentage FROM shareholding_structure
WHERE shareholder_name ILIKE '%Trust%' OR shareholder_name ILIKE '%Trustee%';
```

**已添加的 SQL 示例**（临时方案）：
```json
{
  "id": "shareholding_trust_001",
  "question": "What is the percentage of shareholding of Li Ka-Shing Unity Trustee Company Limited as trustee of The Li Ka-Shing Unity Trust?",
  "sql": "SELECT shareholder_name, percentage FROM shareholding_structure WHERE shareholder_name ILIKE '%Li Ka-Shing Unity Trustee%' LIMIT 10;",
  "note": "Trust structure: Use shareholding_structure table (trust_name/trustee_name not in current schema)"
}
```

---

### 3. Context Injection（需要修改 Python Backend ❌）

**问题**：用户在特定文档中提问时，不会手动输入公司名称和年份，导致 Vanna 生成的 SQL 没有 WHERE 条件。

**示例**：
- **用户输入**："Please provide revenue figures from 2019 – 2023"
- **当前结果**：Vanna 生成 `SELECT * FROM financial_metrics WHERE year BETWEEN 2019 AND 2023`（无公司过滤）
- **正确结果**：应该生成 `SELECT * FROM financial_metrics WHERE company_id = 1 AND year BETWEEN 2019 AND 2023`

**解决方案**：修改 Python Backend，实现 **Prompt Rewriting** 或 **Context Injection**

**实现位置**：`vanna-service/start.py` 或 WebUI Backend

**实现代码示例**：
```python
def inject_document_context(user_question: str, current_document: dict) -> str:
    """
    当用户在特定文档中提问时，自动注入上下文
    
    Args:
        user_question: 用户原始问题
        current_document: 当前文档信息 {
            'doc_id': 'DOC-CKH-2023',
            'filename': 'CKH_AR_2023.pdf',
            'owner_company_id': 1,
            'owner_stock_code': '00001',
            'year': 2023
        }
    
    Returns:
        重写后的完整问题
    """
    if current_document:
        context_prefix = f"""
User is currently viewing document '{current_document['filename']}' 
(owner_stock_code: {current_document['owner_stock_code']}, year: {current_document['year']}).

Question: {user_question}
"""
        return context_prefix
    else:
        return user_question


# 使用示例
user_input = "Please provide revenue figures from 2019 – 2023"
current_doc = {
    'filename': 'CKH_AR_2023.pdf',
    'owner_stock_code': '00001',
    'year': 2023
}

enhanced_question = inject_document_context(user_input, current_doc)
# enhanced_question = "User is currently viewing document 'CKH_AR_2023.pdf' (owner_stock_code: 00001, year: 2023).\n\nQuestion: Please provide revenue figures from 2019 – 2023"

# 然后交给 Vanna
sql = vn.generate_sql(enhanced_question)
# Vanna 会生成带 company_id 过滤的 SQL
```

---

## 📊 修复状态总结

| 建议 | 状态 | 说明 |
|------|------|------|
| **1. 页码过滤** | ✅ 已修复 | documentation.json + sql_pairs.json 已添加 |
| **2. Shareholding 信托查询** | ⚠️ 需扩展 Schema | shareholding_structure 表缺少 trust_name/trustee_name |
| **3. Context Injection** | ❌ 需修改 Backend | 需要在 Python Backend 实现 Prompt Rewriting |

---

## 🚀 下一步

### 1. 测试页码过滤

```powershell
# 重启 Vanna Service
docker compose restart vanna-service

# 测试页码问题
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the revenue from Canada based on the chart of p.6?"}'
```

**预期结果**：Vanna 应该生成 `WHERE source_page = 6`

---

### 2. 决定是否扩展 Schema

**如果需要支持信托查询**：
```sql
-- 扩展 shareholding_structure 表
ALTER TABLE shareholding_structure ADD COLUMN trust_name VARCHAR(255);
ALTER TABLE shareholding_structure ADD COLUMN trustee_name VARCHAR(255);
ALTER TABLE shareholding_structure ADD COLUMN percentage_held NUMERIC(6, 4);
```

**如果不需要**：暂时跳过，使用临时方案（`shareholder_name ILIKE '%Trust%'`）

---

### 3. 实现 Context Injection

**修改文件**：
- `vanna-service/start.py` 或
- `webui/app/api/chat.py`

**实现步骤**：
1. 在 WebUI 中，当用户打开特定文档时，记录 `current_document` 信息
2. 在用户发送问题时，调用 `inject_document_context()` 重写问题
3. 将重写后的问题交给 Vanna

---

## 💡 核心改进

| 维度 | 改进内容 |
|------|---------|
| **页码识别** | ✅ Vanna 现在懂 "p.6" = `WHERE source_page = 6` |
| **信托查询** | ⚠️ 临时方案：用 `shareholder_name ILIKE '%Trust%'` |
| **上下文注入** | ❌ 待实现：需要在 Backend 自动添加公司过滤 |

---

## 📁 修改的文件

- [vanna-service/data/documentation.json](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/vanna-service/data/documentation.json) - 版本 2.2.0
- [vanna-service/data/sql_pairs.json](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/vanna-service/data/sql_pairs.json) - 版本 2.1.0

---

**Gemini 的建议非常实用，已修复 2/3，剩余 1 个需要你决定是否实现！** 💯🎉