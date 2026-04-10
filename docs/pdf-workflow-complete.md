# 📊 Nanobot: PDF 上傳與跨模組工作流程解析 (完整版)

**版本**: 2.0 (Agentic Dynamic Ingestion)  
**最後更新**: 2026-04-10  
**適用範圍**: WebUI + Nanobot + OpenDataLoader + PostgreSQL + Vanna

---

## 🔄 核心工作流程 (The Static ETL Workflow)

### 1. 檔案接收與前置處理 (WebUI)

#### 觸發點
用戶在前端網頁點擊上傳按鈕。

**相關文件**:
- `webui/static/js/ui.js` - 上傳事件監聽器
- `webui/static/js/api.js` - HTTP 請求發送
- `webui/app/api/document.py` - FastAPI 路由
- `webui/app/services/pdf_service.py` - 業務邏輯處理

**前端代碼**:
```javascript
// webui/static/js/ui.js
document.getElementById('upload-btn').addEventListener('click', async () => {
    const fileInput = document.getElementById('file-input');
    const file = fileInput.files[0];
    
    if (!file || file.type !== 'application/pdf') {
        showError('請上傳 PDF 檔案');
        return;
    }
    
    // 發送上傳請求
    const taskId = await uploadPDF(file);
    startPolling(taskId);
});

// webui/static/js/api.js
async function uploadPDF(file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('company_id', document.getElementById('company-id').value);
    formData.append('year', document.getElementById('year').value);
    
    const response = await fetch('/api/documents/upload', {
        method: 'POST',
        body: formData
    });
    
    const result = await response.json();
    return result.task_id;
}
```

**後端路由**:
```python
# webui/app/api/document.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from webui.app.services.pdf_service import PDFService

router = APIRouter()
pdf_service = PDFService()

@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    company_id: int = Form(None),
    year: int = Form(...)
):
    """
    接收 PDF 上傳，返回 task_id
    
    Returns:
        {"task_id": "uuid", "status": "queued"}
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    # 驗證檔案大小 (最大 50MB)
    file.file.seek(0, 2)  # 移動到結尾
    file_size = file.file.tell()
    file.file.seek(0)  # 重置到開頭
    
    if file_size > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 50MB limit")
    
    # 處理上傳
    task_id = await pdf_service.process_uploaded_pdf(
        file=file,
        company_id=company_id,
        year=year
    )
    
    return {"task_id": task_id, "status": "queued"}
```

**業務邏輯**:
```python
# webui/app/services/pdf_service.py
import uuid
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from loguru import logger

class PDFService:
    def __init__(self):
        self.upload_dir = Path("/app/uploads")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
    
    async def process_uploaded_pdf(
        self,
        file,
        company_id: Optional[int] = None,
        year: Optional[int] = None
    ) -> str:
        """
        處理上傳的 PDF 檔案
        
        1. 保存到臨時目錄
        2. 在資料庫建立初始記錄
        3. 發布到消息隊列
        4. 返回 task_id
        """
        task_id = str(uuid.uuid4())
        temp_path = self.upload_dir / f"{task_id}.pdf"
        
        # 1. 保存臨時文件
        with open(temp_path, 'wb') as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"📁 PDF uploaded: {file.filename} -> {temp_path}")
        
        # 2. 創建任務記錄
        await self._create_task_record(
            task_id=task_id,
            file_path=temp_path,
            company_id=company_id,
            year=year,
            status='queued'
        )
        
        # 3. 發布到消息隊列 (非同步處理)
        from nanobot.bus.queue import MessageBus
        bus = MessageBus()
        await bus.publish_inbound(InboundMessage(
            channel="webui",
            content=f"process_pdf:{temp_path}",
            metadata={
                "task_id": task_id,
                "company_id": company_id,
                "year": year,
                "original_filename": file.filename
            }
        ))
        
        logger.info(f"📤 Task {task_id} published to queue")
        return task_id
    
    async def _create_task_record(
        self,
        task_id: str,
        file_path: Path,
        company_id: Optional[int],
        year: Optional[int],
        status: str
    ):
        """在資料庫創建任務記錄"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.transaction() as conn:
                await conn.execute(
                    """
                    INSERT INTO document_tasks 
                    (task_id, file_path, company_id, year, status, created_at)
                    VALUES ($1, $2, $3, $4, $5, NOW())
                    """,
                    task_id, str(file_path), company_id, year, status
                )
        finally:
            await db.close()
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """查詢任務狀態"""
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM document_tasks WHERE task_id = $1",
                    task_id
                )
                return dict(row) if row else None
        finally:
            await db.close()
```

---

### 2. 進入核心資料管線 (Nanobot Ingestion Pipeline)

#### 調度中心
```python
# nanobot/ingestion/pipeline.py
class DocumentPipeline:
    """
    Document Pipeline - 企業級文檔處理管道
    
    Two-Stage LLM Pipeline:
    1. Stage 1 (便宜 & 快速): PageClassifier 語義分類
    2. Stage 2 (昂貴 & 精準): Vision Parser + Financial Agent 只處理相關頁面
    """
    
    def __init__(self, db_client: DBClient = None):
        self.db = db_client or DBClient()
        self.parser = OpenDataLoaderParser()
        self.classifier = PageClassifier()
        self.agent = FinancialAgent()
        self.validator = MathValidator()
    
    async def process(
        self,
        pdf_path: str,
        task_id: str = None,
        company_id: int = None,
        year: int = None
    ) -> ProcessingResult:
        """
        處理單一 PDF 文件
        
        Returns:
            ProcessingResult: 包含處理結果和統計信息
        """
        # 更新任務狀態
        if task_id:
            await self._update_task_status(task_id, 'processing', progress=10)
        
        try:
            # 1. 解析 PDF → Markdown/Tables
            if task_id:
                await self._update_task_status(task_id, 'processing', progress=20)
            
            parsed_doc = await self.parser.parse(pdf_path)
            logger.info(f"📄 Parsed {len(parsed_doc.pages)} pages")
            
            # 2. 分類頁面 (找出財報相關頁面)
            if task_id:
                await self._update_task_status(task_id, 'processing', progress=40)
            
            relevant_pages = await self.classifier.classify(parsed_doc.pages)
            logger.info(f"🎯 Found {len(relevant_pages)} relevant pages")
            
            # 3. 提取結構化數據
            if task_id:
                await self._update_task_status(task_id, 'processing', progress=60)
            
            extracted_data = await self.agent.extract(relevant_pages)
            logger.info(f"📊 Extracted {len(extracted_data.metrics)} metrics")
            
            # 4. 驗證數據
            if task_id:
                await self._update_task_status(task_id, 'processing', progress=80)
            
            validation_result = await self.validator.validate(extracted_data)
            if not validation_result.is_valid:
                logger.warning(f"⚠️ Validation errors: {validation_result.errors}")
            
            # 5. 寫入數據庫
            if task_id:
                await self._update_task_status(task_id, 'processing', progress=90)
            
            await self._save_to_db(
                data=extracted_data,
                company_id=company_id,
                year=year,
                pdf_path=pdf_path
            )
            
            # 6. 完成
            if task_id:
                await self._update_task_status(task_id, 'completed', progress=100)
            
            logger.info(f"✅ Processing completed for {pdf_path}")
            
            return ProcessingResult(
                success=True,
                metrics_count=len(extracted_data.metrics),
                pages_processed=len(relevant_pages),
                validation_errors=validation_result.errors
            )
            
        except Exception as e:
            logger.exception(f"❌ Processing failed: {e}")
            if task_id:
                await self._update_task_status(task_id, 'failed', error=str(e))
            raise
        
        finally:
            await self.db.close()
    
    async def _update_task_status(
        self,
        task_id: str,
        status: str,
        progress: int = None,
        error: str = None
    ):
        """更新任務狀態"""
        async with self.db.transaction() as conn:
            if error:
                await conn.execute(
                    """
                    UPDATE document_tasks 
                    SET status = $2, error_message = $3, updated_at = NOW()
                    WHERE task_id = $1
                    """,
                    task_id, status, error
                )
            else:
                updates = ["status = $2", "updated_at = NOW()"]
                params = [task_id, status]
                
                if progress is not None:
                    updates.append("progress = $3")
                    params.append(progress)
                
                await conn.execute(
                    f"UPDATE document_tasks SET {', '.join(updates)} WHERE task_id = $1",
                    *params
                )
```

#### 批次處理
```python
# nanobot/ingestion/batch_processor.py
import asyncio
from typing import List, Optional
from loguru import logger

class BatchProcessor:
    """
    處理大批量 PDF 檔案的排程器
    
    特點:
    - 控制並發數量
    - 錯誤隔離
    - 進度追蹤
    """
    
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.pipeline = DocumentPipeline()
    
    async def process_batch(
        self,
        pdf_paths: List[str],
        task_ids: List[str] = None,
        company_ids: List[int] = None,
        years: List[int] = None
    ) -> BatchResult:
        """
        批次處理多個 PDF 檔案
        
        Args:
            pdf_paths: PDF 文件路徑列表
            task_ids: 任務 ID 列表 (可選)
            company_ids: 公司 ID 列表 (可選)
            years: 年份列表 (可選)
        
        Returns:
            BatchResult: 包含成功/失敗統計
        """
        logger.info(f"📦 Starting batch processing for {len(pdf_paths)} files")
        
        # 創建任務
        tasks = []
        for i, path in enumerate(pdf_paths):
            task = self._process_with_semaphore(
                pdf_path=path,
                task_id=task_ids[i] if task_ids else None,
                company_id=company_ids[i] if company_ids else None,
                year=years[i] if years else None,
                index=i
            )
            tasks.append(task)
        
        # 執行所有任務
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 統計結果
        success_count = sum(1 for r in results if isinstance(r, ProcessingResult) and r.success)
        failure_count = len(results) - success_count
        
        logger.info(f"✅ Batch completed: {success_count} success, {failure_count} failed")
        
        return BatchResult(
            total=len(pdf_paths),
            success=success_count,
            failure=failure_count,
            results=results
        )
    
    async def _process_with_semaphore(
        self,
        pdf_path: str,
        task_id: str = None,
        company_id: int = None,
        year: int = None,
        index: int = 0
    ) -> ProcessingResult:
        """使用信號量控制並發"""
        async with self.semaphore:
            logger.info(f"📄 [{index+1}] Processing {pdf_path}")
            try:
                result = await self.pipeline.process(
                    pdf_path=pdf_path,
                    task_id=task_id,
                    company_id=company_id,
                    year=year
                )
                logger.info(f"✅ [{index+1}] Completed {pdf_path}")
                return result
            except Exception as e:
                logger.exception(f"❌ [{index+1}] Failed {pdf_path}: {e}")
                return ProcessingResult(success=False, error=str(e))
```

---

### 3. 結構化資料提取 (OpenDataLoader)

```python
# nanobot/ingestion/parsers/opendataloader_parser.py
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger

@dataclass
class BoundingBox:
    """邊界框座標"""
    x1: float  # 左上角 X
    y1: float  # 左上角 Y
    x2: float  # 右下角 X
    y2: float  # 右下角 Y
    page: int  # 頁碼
    
    def to_dict(self) -> Dict:
        return {
            "x1": self.x1, "y1": self.y1,
            "x2": self.x2, "y2": self.y2,
            "page": self.page
        }

@dataclass
class ParsedElement:
    """解析後的元素"""
    type: str  # 'text', 'table', 'image'
    content: str
    bbox: Optional[BoundingBox]
    metadata: Dict[str, Any] = None

@dataclass
class ParsedPage:
    """解析後的頁面"""
    page_num: int
    elements: List[ParsedElement]
    markdown_content: str
    tables: List[Dict]
    images: List[Dict]

@dataclass
class ParsedDocument:
    """解析後的文檔"""
    file_path: str
    total_pages: int
    pages: List[ParsedPage]

class OpenDataLoaderParser:
    """
    OpenDataLoader PDF 解析器
    
    特點:
    - 精準解析表格 (Tables)
    - 保持正確的閱讀順序 (Reading order)
    - 輸出邊界框 (Bounding Boxes) 用於溯源
    """
    
    async def parse(self, pdf_path: str) -> ParsedDocument:
        """
        解析 PDF 文件
        
        Returns:
            ParsedDocument: 包含所有解析結果
        """
        logger.info(f"📖 Parsing PDF: {pdf_path}")
        
        try:
            from opendataloader import parse_pdf
            
            # 調用 OpenDataLoader
            result = parse_pdf(pdf_path)
            
            # 轉換為內部格式
            pages = []
            for page_data in result.pages:
                page = ParsedPage(
                    page_num=page_data.page_num,
                    elements=[
                        ParsedElement(
                            type=elem.type,
                            content=elem.content,
                            bbox=BoundingBox(
                                x1=elem.bbox.x1,
                                y1=elem.bbox.y1,
                                x2=elem.bbox.x2,
                                y2=elem.bbox.y2,
                                page=page_data.page_num
                            ) if elem.bbox else None,
                            metadata=elem.metadata
                        )
                        for elem in page_data.elements
                    ],
                    markdown_content=page_data.markdown,
                    tables=page_data.tables,
                    images=page_data.images
                )
                pages.append(page)
            
            parsed_doc = ParsedDocument(
                file_path=pdf_path,
                total_pages=len(pages),
                pages=pages
            )
            
            logger.info(f"✅ Parsed {parsed_doc.total_pages} pages, "
                       f"{sum(len(p.tables) for p in pages)} tables")
            
            return parsed_doc
            
        except Exception as e:
            logger.exception(f"❌ Failed to parse PDF: {e}")
            raise
```

---

### 4. 數據清洗與資料庫存儲 (PostgreSQL)

```python
# nanobot/ingestion/extractors/value_normalizer.py
import re
from typing import Optional, Tuple
from decimal import Decimal

class ValueNormalizer:
    """
    數值正規化：統一單位、貨幣、小數點
    """
    
    CURRENCY_RATES = {
        'HKD': 1.0,
        'USD': 7.8,
        'RMB': 0.92,
        'EUR': 8.5
    }
    
    def normalize_value(self, value: str, context: Dict) -> NormalizedValue:
        """
        正規化單一數值
        
        Args:
            value: 原始數值字符串 (如 "1,234.56 百萬")
            context: 上下文信息 (unit, currency 等)
        
        Returns:
            NormalizedValue: 標準化後的數值
        """
        # 1. 清理字符串
        cleaned = re.sub(r'[,%\s]', '', value)
        
        # 2. 提取數字
        match = re.search(r'[-+]?\d*\.?\d+', cleaned)
        if not match:
            raise ValueError(f"Cannot parse number from: {value}")
        
        num = Decimal(match.group())
        
        # 3. 應用單位倍數
        unit = context.get('unit', 'base').lower()
        if 'million' in unit or '百萬' in unit:
            num *= Decimal('1000000')
        elif 'billion' in unit or '十億' in unit:
            num *= Decimal('1000000000')
        elif 'thousand' in unit or '千' in unit:
            num *= Decimal('1000')
        
        # 4. 轉換貨幣為基準貨幣 (HKD)
        currency = context.get('currency', 'HKD').upper()
        if currency in self.CURRENCY_RATES:
            num *= Decimal(str(self.CURRENCY_RATES[currency]))
        
        return NormalizedValue(
            value=float(num),
            original_value=value,
            currency='HKD',
            unit='base'
        )

# nanobot/ingestion/validators/math_rules.py
class MathValidator:
    """
    數學規則驗證：確保財報數字自洽
    """
    
    async def validate(self, data: FinancialData) -> ValidationResult:
        """
        驗證財務數據
        
        Rules:
        1. 總計 = 各分項之和
        2. 資產 = 負債 + 權益
        3. 現金流表平衡
        """
        errors = []
        warnings = []
        
        # 規則 1: 收入明細總和應等於總收入
        if data.revenue_breakdown:
            total = sum(item.amount for item in data.revenue_breakdown)
            if not self._is_close(total, data.total_revenue, tolerance=0.01):
                errors.append(
                    f"Revenue breakdown sum mismatch: {total} vs {data.total_revenue}"
                )
        
        # 規則 2: 資產負債表平衡
        if data.balance_sheet:
            assets = data.balance_sheet.total_assets
            liabilities = data.balance_sheet.total_liabilities
            equity = data.balance_sheet.total_equity
            
            if assets and liabilities and equity:
                if not self._is_close(assets, liabilities + equity, tolerance=1000):
                    warnings.append(
                        f"Balance sheet doesn't balance: {assets} vs {liabilities + equity}"
                    )
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def _is_close(self, a: float, b: float, tolerance: float = 0.01) -> bool:
        """檢查兩個數值是否接近"""
        if a == 0 and b == 0:
            return True
        return abs(a - b) / max(abs(a), abs(b)) <= tolerance
```

---

### 5. 自然語言查詢轉換 (Vanna AI)

```python
# nanobot/agent/tools/vanna_tool.py (已修復版本)
class VannaSQL:
    """
    Vanna AI Text-to-SQL 生成器
    
    功能:
    1. 自動訓練資料庫 Schema
    2. 生成 SQL 查詢
    3. 執行並格式化結果
    """
    
    async def query(self, question: str) -> QueryResult:
        """
        執行自然語言查詢
        
        Flow:
        1. 確保已訓練
        2. 生成 SQL
        3. 驗證安全性
        4. 執行查詢
        5. 格式化結果
        """
        # 1. 確保已訓練
        if not self._trained:
            await self.train_schema()
        
        # 2. 生成 SQL
        sql = self.vn.generate_sql(question)
        logger.info(f"🔍 Generated SQL: {sql[:200]}...")
        
        # 3. 驗證 SQL 安全性
        is_safe, reason = self._validate_sql(sql)
        if not is_safe:
            raise SecurityError(f"Unsafe SQL: {reason}")
        
        # 4. 執行查詢
        results = await self._execute_sql(sql)
        
        # 5. 格式化結果
        return QueryResult(
            sql=sql,
            data=results,
            explanation=self._explain_query(question, sql, results)
        )
```

---

## 🚀 進階架構：Agentic Dynamic Ingestion

### 架構設計理念

傳統 ETL 流程的問題：
- ❌ Schema 固定，無法適應多變的財報格式
- ❌ 遇到新欄位需要手動 ALTER TABLE
- ❌ 無法處理「無母公司」的特殊報告 (如恒指報告)

Agentic Dynamic Ingestion 的優勢：
- ✅ AI 動態判斷 Schema 需求
- ✅ JSONB 存儲動態屬性，避免無限寬表
- ✅ 自動識別複雜實體關係

---

### 實作流程

#### Step 1: 首頁掃描與實體識別

```python
# nanobot/ingestion/agents/ingestion_agent.py
from nanobot.agent.loop import AgentLoop
from typing import List, Dict, Any

class IngestionSubAgent:
    """
    專門用於數據入庫的子代理
    
    職責:
    1. 分析 PDF 前 1-2 頁
    2. 提取實體信息 (公司、行業、關係)
    3. 決策 Schema 需求
    4. 協調寫入流程
    """
    
    def __init__(self, parent_loop: AgentLoop):
        self.parent_loop = parent_loop
        self.tools = self._setup_tools()
    
    def _setup_tools(self) -> List[BaseTool]:
        """設置專用的 Tool 集合"""
        return [
            SchemaReflectionTool(),      # 反射當前 Schema
            EntityExtractionTool(),       # 提取實體信息
            DynamicInsertTool(),          # 動態插入數據
            RelationshipMappingTool(),    # 建立關係映射
            JSONBWriteTool()              # 寫入 JSONB 欄位
        ]
    
    async def analyze_document(
        self,
        pdf_path: str,
        task_id: str = None
    ) -> DocumentAnalysis:
        """
        分析文檔前 1-2 頁，提取關鍵實體
        
        Returns:
            DocumentAnalysis: 包含公司、行業、關係等信息
        """
        # 1. 解析前 2 頁
        parser = OpenDataLoaderParser()
        parsed_doc = await parser.parse(pdf_path)
        first_pages = parsed_doc.pages[:2]
        
        # 2. 轉換為 Markdown 供 AI 分析
        context = "\n\n".join([
            f"=== Page {p.page_num} ===\n{p.markdown_content}"
            for p in first_pages
        ])
        
        # 3. 呼叫 AI 分析
        prompt = f"""
你是一個專業的財報分析助手。請分析以下文檔內容，提取關鍵實體信息：

{context}

請提取：
1. 母公司 (Parent Company) - 可能為 Null (如恒指報告)
2. 子公司列表 (Subsidiaries) - 一份文檔可能包含多間公司
3. 行業別 (Industry) - 可能有多個
4. 文檔類型 (Document Type) - 年報/季報/恒指報告等
5. 年份 (Fiscal Year)

以 JSON 格式返回：
{{
    "parent_company": {{
        "name_en": "...",
        "name_zh": "...",
        "stock_code": "..."
    }},
    "subsidiaries": [
        {{"name": "...", "stock_code": "..."}}
    ],
    "industries": ["...", "..."],
    "document_type": "...",
    "year": 2024,
    "is_index_report": true/false
}}
"""
        
        # 4. 執行 AI 分析
        from nanobot.providers.base import LLMProvider
        provider = self.parent_loop.provider
        response = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            model=self.parent_loop.model
        )
        
        # 5. 解析結果
        import json
        try:
            analysis = json.loads(response.content)
            return DocumentAnalysis(**analysis)
        except Exception as e:
            logger.error(f"Failed to parse AI response: {e}")
            raise

@dataclass
class DocumentAnalysis:
    """文檔分析結果"""
    parent_company: Optional[Dict]
    subsidiaries: List[Dict]
    industries: List[str]
    document_type: str
    year: int
    is_index_report: bool
```

#### Step 2: Schema 動態反射與評估

```python
# nanobot/agent/tools/schema.py
from nanobot.agent.tools.base import BaseTool
from typing import Dict, List

class SchemaReflectionTool(BaseTool):
    """
    反射數據庫 Schema
    
    功能:
    1. 獲取當前表結構
    2. 檢查欄位是否存在
    3. 建議是否需要新增欄位
    """
    
    name = "schema_reflection"
    description = "Reflect on the current database schema"
    
    async def execute(self, table_name: str) -> Dict:
        """
        反射指定表的 Schema
        
        Args:
            table_name: 表名
        
        Returns:
            {
                "columns": [{"name": "...", "type": "...", "nullable": true}],
                "indexes": [...],
                "suggestions": [...]
            }
        """
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.connection() as conn:
                # 獲取欄位信息
                columns = await conn.fetch(
                    """
                    SELECT 
                        column_name,
                        data_type,
                        is_nullable,
                        column_default
                    FROM information_schema.columns
                    WHERE table_name = $1
                    ORDER BY ordinal_position
                    """,
                    table_name
                )
                
                # 獲取索引信息
                indexes = await conn.fetch(
                    """
                    SELECT 
                        indexname,
                        indexdef
                    FROM pg_indexes
                    WHERE tablename = $1
                    """,
                    table_name
                )
                
                return {
                    "columns": [dict(col) for col in columns],
                    "indexes": [dict(idx) for idx in indexes],
                    "suggestions": self._generate_suggestions(columns)
                }
        finally:
            await db.close()
    
    def _generate_suggestions(self, columns: List) -> List[str]:
        """生成 Schema 優化建議"""
        suggestions = []
        
        # 檢查是否有 JSONB 欄位
        has_jsonb = any(col['data_type'] == 'jsonb' for col in columns)
        if not has_jsonb:
            suggestions.append(
                "Consider adding a JSONB column for dynamic attributes"
            )
        
        # 檢查是否有索引
        if len(columns) > 5:
            suggestions.append(
                "Consider adding indexes on frequently queried columns"
            )
        
        return suggestions


class JSONBWriteTool(BaseTool):
    """
    寫入 JSONB 欄位
    
    功能:
    1. 動態寫入 Key-Value 對
    2. 自動合併現有 JSON
    3. 支持嵌套結構
    """
    
    name = "jsonb_write"
    description = "Write data to a JSONB column"
    
    async def execute(
        self,
        table_name: str,
        record_id: int,
        column_name: str,
        data: Dict,
        merge: bool = True
    ) -> bool:
        """
        寫入 JSONB 數據
        
        Args:
            table_name: 表名
            record_id: 記錄 ID
            column_name: JSONB 欄位名
            data: 要寫入的數據
            merge: 是否合併現有數據 (vs 覆蓋)
        
        Returns:
            bool: 是否成功
        """
        from nanobot.ingestion.repository.db_client import DBClient
        import json
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.transaction() as conn:
                if merge:
                    # 合併現有 JSON
                    await conn.execute(
                        f"""
                        UPDATE {table_name}
                        SET {column_name} = COALESCE({column_name}, '{{}}'::jsonb) || $1
                        WHERE id = $2
                        """,
                        json.dumps(data),
                        record_id
                    )
                else:
                    # 覆蓋寫入
                    await conn.execute(
                        f"""
                        UPDATE {table_name}
                        SET {column_name} = $1
                        WHERE id = $2
                        """,
                        json.dumps(data),
                        record_id
                    )
                
                logger.info(f"✅ Wrote JSONB data to {table_name}.{column_name}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to write JSONB: {e}")
            return False
        finally:
            await db.close()
```

#### Step 3: 動態資料寫入

```python
# nanobot/ingestion/agents/dynamic_writer.py
from typing import Dict, Any, List, Optional

class DynamicDataWriter:
    """
    動態數據寫入器
    
    策略:
    1. 核心欄位 → 實體欄位 (parent_company, confirmed_industry, etc.)
    2. 動態屬性 → JSONB 欄位 (zone1_raw_data)
    3. AI 判斷 → 保留人工覆核機制
    """
    
    async def write_company_with_dynamic_attrs(
        self,
        analysis: DocumentAnalysis,
        extracted_data: ExtractedData,
        source_file: str
    ) -> int:
        """
        寫入公司數據 (包含動態屬性)
        
        Flow:
        1. 檢查公司是否存在
        2. 寫入核心欄位
        3. 寫入 JSONB 動態屬性
        4. 標記待覆核狀態
        """
        from nanobot.ingestion.repository.db_client import DBClient
        
        db = DBClient()
        await db.connect()
        
        try:
            async with db.transaction() as conn:
                # 1. 檢查/創建公司記錄
                if analysis.parent_company:
                    company_id = await self._upsert_company(
                        conn=conn,
                        company=analysis.parent_company,
                        analysis=analysis,
                        source_file=source_file
                    )
                else:
                    # 無母公司 (如恒指報告)
                    company_id = None
                
                # 2. 寫入動態屬性到 JSONB
                if company_id:
                    await self._write_dynamic_attributes(
                        conn=conn,
                        company_id=company_id,
                        extracted_data=extracted_data,
                        ai_analysis=analysis
                    )
                
                # 3. 創建待覆核記錄
                await self._create_review_record(
                    conn=conn,
                    company_id=company_id,
                    analysis=analysis,
                    source_file=source_file
                )
                
                return company_id
                
        finally:
            await db.close()
    
    async def _upsert_company(
        self,
        conn,
        company: Dict,
        analysis: DocumentAnalysis,
        source_file: str
    ) -> int:
        """Upsert 公司記錄"""
        stock_code = company.get('stock_code', '').zfill(5)
        
        # 檢查是否存在
        existing = await conn.fetchrow(
            "SELECT id FROM companies WHERE stock_code = $1",
            stock_code
        )
        
        if existing:
            # 更新現有記錄
            await conn.execute(
                """
                UPDATE companies
                SET 
                    name_en_extracted = COALESCE($2, name_en_extracted),
                    name_zh_extracted = COALESCE($3, name_zh_extracted),
                    updated_at = NOW()
                WHERE id = $1
                """,
                existing['id'],
                company.get('name_en'),
                company.get('name_zh')
            )
            return existing['id']
        else:
            # 創建新記錄
            result = await conn.fetchrow(
                """
                INSERT INTO companies (
                    stock_code,
                    name_en_extracted,
                    name_zh_extracted,
                    sector,
                    industry,
                    listing_status,
                    created_at
                ) VALUES ($1, $2, $3, $4, $5, 'listed', NOW())
                RETURNING id
                """,
                stock_code,
                company.get('name_en'),
                company.get('name_zh'),
                analysis.industries[0] if analysis.industries else 'Unknown',
                analysis.industries[0] if analysis.industries else 'Unknown'
            )
            return result['id']
    
    async def _write_dynamic_attributes(
        self,
        conn,
        company_id: int,
        extracted_data: ExtractedData,
        ai_analysis: DocumentAnalysis
    ):
        """寫入動態屬性到 JSONB 欄位"""
        import json
        
        # 組合動態數據
        dynamic_data = {
            "ai_extracted": {
                "industries": ai_analysis.industries,
                "document_type": ai_analysis.document_type,
                "is_index_report": ai_analysis.is_index_report
            },
            "extraction_metadata": {
                "metrics_count": len(extracted_data.metrics),
                "tables_count": len(extracted_data.tables),
                "extraction_timestamp": datetime.now().isoformat()
            },
            "raw_data": {
                # 保留原始提取數據供後續處理
                "metrics": [m.to_dict() for m in extracted_data.metrics],
                "tables": extracted_data.tables
            }
        }
        
        # 寫入 JSONB 欄位
        await conn.execute(
            """
            UPDATE companies
            SET zone1_raw_data = COALESCE(zone1_raw_data, '{}'::jsonb) || $1
            WHERE id = $2
            """,
            json.dumps(dynamic_data),
            company_id
        )
    
    async def _create_review_record(
        self,
        conn,
        company_id: Optional[int],
        analysis: DocumentAnalysis,
        source_file: str
    ):
        """創建待覆核記錄"""
        await conn.execute(
            """
            INSERT INTO data_review_queue (
                company_id,
                review_type,
                status,
                ai_suggestions,
                source_file,
                created_at
            ) VALUES ($1, $2, 'pending', $3, $4, NOW())
            """,
            company_id,
            'industry_confirmation',
            json.dumps({
                "ai_industries": analysis.industries,
                "confidence": "high" if len(analysis.industries) == 1 else "medium"
            }),
            source_file
        )
```

---

### 數據庫 Schema 設計

```sql
-- 公司表 (增強版)
CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    
    -- 核心欄位 (實體)
    stock_code VARCHAR(20) UNIQUE,
    name_en_index VARCHAR(255),        -- 恆指報表來源
    name_en_extracted VARCHAR(255),    -- PDF 擷取來源
    name_zh_extracted VARCHAR(255),
    
    -- 行業信息
    sector VARCHAR(100),
    industry VARCHAR(100),
    ai_extracted_industries JSONB,     -- AI 提取的多個行業
    confirmed_industry VARCHAR(100),   -- 人工確認後的行業
    
    -- 動態屬性 (JSONB)
    zone1_raw_data JSONB,              -- Zone 1 原始數據
    dynamic_attributes JSONB,          -- 其他動態屬性
    
    -- 審計欄位
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 創建索引
CREATE INDEX idx_companies_stock_code ON companies(stock_code);
CREATE INDEX idx_companies_industry ON companies(industry);
CREATE INDEX idx_companies_zone1_raw_data ON companies USING GIN(zone1_raw_data);

-- 待覆核隊列
CREATE TABLE data_review_queue (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    review_type VARCHAR(50),           -- 'industry_confirmation', 'data_validation'
    status VARCHAR(20),                -- 'pending', 'approved', 'rejected'
    ai_suggestions JSONB,              -- AI 建議
    human_feedback TEXT,               -- 人工反饋
    source_file VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(100)
);

-- 文檔任務表
CREATE TABLE document_tasks (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(100) UNIQUE,
    file_path VARCHAR(500),
    company_id INTEGER,
    year INTEGER,
    status VARCHAR(20),                -- 'queued', 'processing', 'completed', 'failed'
    progress INTEGER DEFAULT 0,        -- 0-100
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### 可行性評估總結

| 評估面向 | 評分 | 分析結果 | 建議對策 |
|----------|------|----------|----------|
| 技術可行性 | ⭐⭐⭐⭐⭐ | 極高 | 現有架構已具備基礎，只需擴充 Tool |
| 架構彈性 | ⭐⭐⭐⭐⭐ | 極高 | JSONB + 實體欄位混用，避免無限寬表 |
| 數據準確度 | ⭐⭐⭐⭐ | 中高 | 需要 confirmed_industry 雙重確認機制 |
| 效能考量 | ⭐⭐⭐ | 中低 | AI 只做 Schema 決策，大量數據仍用 Python 批次寫入 |

---

## 📋 實作檢查清單

### Phase 1: 基礎建設 (1-2 週)
- [ ] 創建 `IngestionSubAgent` 類
- [ ] 實現 `SchemaReflectionTool`
- [ ] 實現 `JSONBWriteTool`
- [ ] 更新數據庫 Schema (添加 JSONB 欄位)
- [ ] 創建 `data_review_queue` 表

### Phase 2: 核心功能 (2-3 週)
- [ ] 實現首頁掃描與實體識別
- [ ] 實現動態數據寫入流程
- [ ] 添加待覆核機制
- [ ] 前端覆核界面

### Phase 3: 優化與監控 (1-2 週)
- [ ] 添加性能監控
- [ ] 優化 AI 提示詞
- [ ] 添加單元測試
- [ ] 文檔完善

---

## 🔗 相關文檔

- [Server Startup Workflow](./server-startup-workflow.md)
- [Code Fixes Summary](./code-fixes-summary.md)
- [Database Schema](./database-schema.md)

---

**版本**: 2.0  
**最後更新**: 2026-04-10  
**狀態**: 設計完成，待實作
