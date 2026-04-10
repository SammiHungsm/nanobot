# Python 代码修复总结 - db_client.py

## ✅ 验证结果

```
[PASS] 1. create_document 修复
[PASS] 2. update_document_company_id 修复
[PASS] 3. add_mentioned_company 新方法
[PASS] 4. 无其他旧字段名错误

通过验证: 4/4
完成度: 100.0%
```

---

## 📝 详细修复内容

### 修复 1：`create_document` 方法

**修复位置**：[nanobot/ingestion/repository/db_client.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/nanobot/ingestion/repository/db_client.py) 第 814 行

**修复前**：
```python
async def create_document(
    self,
    doc_id: str,
    company_id: Optional[int],
    title: str,
    file_path: str,
    file_hash: str,
    file_size: int,
    document_type: str = "annual_report"
):
    """創建文檔記錄"""
    await self.conn.execute(
        """
        INSERT INTO documents (
            doc_id, company_id, filename, title, document_type, 
            file_path, file_hash, file_size_bytes,
            processing_status, status, uploaded_at
        ) VALUES (...)
        """,
        doc_id,
        company_id,  # ❌ 错误：字段不存在
        filename,
        title,  # ❌ 错误：字段已删除
        ...
    )
```

**修复后**：
```python
async def create_document(
    self,
    doc_id: str,
    company_id: Optional[int],  # 這裡傳入的其實是母公司 ID
    title: str,  # 保留參數以防其他地方報錯，但不寫入 DB
    file_path: str,
    file_hash: str,
    file_size: int,
    document_type: str = "annual_report"  # 保持參數名不變以防其他地方報錯
):
    """創建文檔記錄 (適配新 Schema)"""
    await self.conn.execute(
        """
        INSERT INTO documents (
            doc_id, owner_company_id, filename, file_path, file_hash, 
            file_size_bytes, report_type, processing_status, uploaded_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
        ON CONFLICT (doc_id) DO UPDATE SET
            processing_status = 'pending',
            updated_at = NOW()
        """,
        doc_id,
        company_id,  # ✅ 写入 owner_company_id
        filename,
        file_path,
        file_hash,
        file_size,  # ✅ 写入 file_size_bytes
        document_type,  # ✅ 写入 report_type
        "pending"
    )
```

**关键改进**：
- ✅ `company_id` → `owner_company_id`
- ✅ `document_type` → `report_type`
- ✅ 删除了 `title` 和 `status` 字段（新 Schema 中不存在）
- ✅ 保留参数名不变（防止其他地方报错）

---

### 修复 2：`update_document_company_id` 方法

**修复位置**：[nanobot/ingestion/repository/db_client.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/nanobot/ingestion/repository/db_client.py) 第 902 行

**修复前**：
```python
async def update_document_company_id(self, doc_id: str, company_id: int, year: int = None):
    """更新文檔的公司 ID 和年份"""
    await self.conn.execute(
        """
        UPDATE documents SET
            company_id = $1,  # ❌ 错误：字段不存在
            year = $2,
            updated_at = NOW()
        WHERE doc_id = $3
        """,
        company_id,
        year,
        doc_id
    )
    logger.info(f"✅ 已更新文檔 {doc_id} 的 company_id={company_id}")
```

**修复后**：
```python
async def update_document_company_id(self, doc_id: str, company_id: int, year: int = None):
    """更新文檔的母公司 ID 和年份"""
    await self.conn.execute(
        """
        UPDATE documents SET
            owner_company_id = $1,  # ✅ 正确字段名
            year = $2,
            updated_at = NOW()
        WHERE doc_id = $3
        """,
        company_id,
        year,
        doc_id
    )
    logger.info(f"✅ 已更新文檔 {doc_id} 的 owner_company_id={company_id}")
```

**关键改进**：
- ✅ `company_id` → `owner_company_id`
- ✅ 更新日志信息

---

### 修复 3：新增 `add_mentioned_company` 方法

**修复位置**：[nanobot/ingestion/repository/db_client.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/nanobot/ingestion/repository/db_client.py) 第 290 行（插入到 `upsert_company` 后）

**新增方法**：
```python
async def add_mentioned_company(
    self,
    document_id: int,
    company_id: int,
    relation_type: str = "mentioned",
    extracted_industries: list = None,
    extraction_source: str = "ai_predict"
) -> bool:
    """
    🎯 記錄 PDF 中提及的公司 (寫入橋樑表)
    
    Args:
        document_id: documents 表的 ID (不是 doc_id 字串，是 Integer ID)
        company_id: companies 表的 ID
        relation_type: 關係類型 (如 'subsidiary', 'competitor', 'index_constituent', 'mentioned')
        extracted_industries: 提取到的行業列表 (例如 ["Gaming", "Cloud"])
        extraction_source: 來源 ('ai_predict' 或 'index_rule')
        
    Returns:
        bool: 是否成功
    """
    import json
    
    industries_json = json.dumps(extracted_industries) if extracted_industries else None
    
    try:
        await self.conn.execute(
            """
            INSERT INTO document_companies (
                document_id, company_id, relation_type, 
                extracted_industries, extraction_source
            ) VALUES ($1, $2, $3, $4::jsonb, $5)
            ON CONFLICT (document_id, company_id) DO UPDATE SET
                relation_type = $3,
                extracted_industries = $4::jsonb,
                extraction_source = $5
            """,
            document_id,
            company_id,
            relation_type,
            industries_json,
            extraction_source
        )
        logger.info(f"✅ 已記錄提及公司: doc_id={document_id}, company_id={company_id}, relation={relation_type}")
        return True
    except Exception as e:
        logger.error(f"❌ 寫入 document_companies 失敗: {e}")
        return False
```

**关键功能**：
- ✅ 写入橋樑表 `document_companies`
- ✅ 支持 `relation_type` 区分关系类型
- ✅ 支持 JSONB 存储行业数据
- ✅ 返回 bool 表示成功/失败
- ✅ ON CONFLICT 确保幂等性

---

## 💡 使用示例

### 1. 使用 `create_document`

```python
from nanobot.ingestion.repository.db_client import DBClient

db = DBClient()
await db.connect()

# 创建文档记录
await db.create_document(
    doc_id="annual_report_2023_00700",
    company_id=123,  # 腾讯的公司 ID
    title="Tencent Holdings Limited Annual Report 2023",  # 参数保留但不写入
    file_path="/data/uploads/00700_2023.pdf",
    file_hash="abc123",
    file_size=1024000,
    document_type="annual_report"
)
```

---

### 2. 使用 `update_document_company_id`

```python
# 更新文档的母公司 ID
await db.update_document_company_id(
    doc_id="annual_report_2023_00700",
    company_id=123,
    year=2023
)
```

---

### 3. 使用 `add_mentioned_company`

```python
# 记录 PDF 中提及的公司
await db.add_mentioned_company(
    document_id=456,  # documents 表的 Integer ID
    company_id=789,  # 提及的公司 ID
    relation_type="subsidiary",  # 关系类型
    extracted_industries=["Gaming", "Cloud"],  # 提取的行业
    extraction_source="ai_predict"  # 来源
)
```

---

## 📊 修复对比

| 维度 | 修复前 | 修复后 |
|------|--------|--------|
| **字段名** | `company_id` | ✅ `owner_company_id` |
| **字段名** | `document_type` | ✅ `report_type` |
| **字段名** | `title` | ✅ 删除（新 Schema 无此字段） |
| **橋樑表** | 不支持 | ✅ 新增 `add_mentioned_company()` |
| **relation_type** | 不支持 | ✅ 支持区分关系类型 |
| **JSONB 行业** | 不支持 | ✅ 支持 `extracted_industries` |
| **幂等性** | ON CONFLICT | ✅ ON CONFLICT |

---

## 🎯 核心改进

1. **Python 代码与数据库 Schema 完全同步**
   - ✅ 所有字段名已适配新 Schema
   - ✅ 删除了不存在的字段

2. **支持 owner_company_id（母公司概念）**
   - ✅ 区分母公司和提及公司
   - ✅ 支持恒生指数报告（owner_company_id 可为 NULL）

3. **支持橋樑表 document_companies**
   - ✅ 新增 `add_mentioned_company()` 方法
   - ✅ 记录 PDF 中提及的所有公司

4. **支持 relation_type 区分关系类型**
   - ✅ `index_constituent`：恒生指数成分股
   - ✅ `subsidiary`：子公司
   - ✅ `competitor`：竞争对手
   - ✅ `mentioned`：一般提及

---

## 📁 修改的文件

- [nanobot/ingestion/repository/db_client.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/nanobot/ingestion/repository/db_client.py)

---

## 🚀 下一步

### 1. 测试 PDF 上传流程

```python
# 测试完整流程
from nanobot.ingestion.pipeline import DocumentPipeline

pipeline = DocumentPipeline(db_url, data_dir)
await pipeline.connect()

result = await pipeline.process_pdf_full(
    pdf_path="/data/uploads/test.pdf",
    company_id=None,  # 让 Vision LLM 自动提取
    doc_id="test_doc"
)
```

### 2. 验证数据库写入

```sql
-- 检查文档记录
SELECT id, doc_id, owner_company_id, report_type FROM documents;

-- 检查橋樑表
SELECT document_id, company_id, relation_type, extracted_industries 
FROM document_companies;
```

### 3. 测试 Agent 调用

```python
# Agent 发现新公司时调用
await db.add_mentioned_company(
    document_id=doc['id'],
    company_id=new_company['id'],
    relation_type="competitor",
    extracted_industries=["AI", "Robotics"],
    extraction_source="ai_predict"
)
```

---

## 💾 验证文件

- [verify_db_client_fix.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/verify_db_client_fix.py)

---

## 📚 相关文档

- [SQL_SCHEMA_FIX_SUMMARY.md](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/docs/SQL_SCHEMA_FIX_SUMMARY.md)
- [Vanna Training Data 验证](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/verify_vanna_training_complete.py)

---

**Python 代码现已与数据库 Schema 完全同步，支持所有新特性！** 🎉