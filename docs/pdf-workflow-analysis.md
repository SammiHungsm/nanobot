# 📊 Nanobot: PDF 上傳與跨模組工作流程解析 (Workflow)

**版本**: 1.0  
**最後更新**: 2026-04-10  
**適用範圍**: WebUI + Nanobot + OpenDataLoader + PostgreSQL + Vanna

---

## 🔄 核心工作流程 (The Workflow)

### 1. 檔案接收與前置處理 (WebUI)

#### 觸發點
用戶在前端網頁上傳 PDF 檔案。

**相關文件**:
- `webui/static/index.html` - 上傳界面
- `webui/static/ui.js` - 前端邏輯
- `webui/app/api/document.py` - FastAPI 路由

#### API 接收
```python
# webui/app/api/document.py
@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    company_id: int = Form(None),
    year: int = Form(...)
):
    """接收 PDF 上傳，返回 task_id"""
    task_id = await pdf_service.queue_processing(file, company_id, year)
    return {"task_id": task_id, "status": "queued"}
```

#### 業務邏輯
```python
# webui/app/services/pdf_service.py
class PDFService:
    async def queue_processing(self, file, company_id, year):
        # 1. 驗證文件 (PDF 格式、大小限制)
        await self._validate_file(file)
        
        # 2. 保存到臨時目錄
        temp_path = await self._save_temp(file)
        
        # 3. 發布到消息隊列
        task_id = await self.bus.publish_inbound(InboundMessage(
            channel="webui",
            content=f"process_pdf:{temp_path}",
            metadata={"company_id": company_id, "year": year}
        ))
        
        return task_id
```

---

### 2. 進入核心資料管線 (Nanobot Ingestion Pipeline)

#### 調度中心
```python
# nanobot/ingestion/pipeline.py
class DocumentPipeline:
    """
    Two-Stage LLM Pipeline:
    1. Stage 1 (便宜 & 快速): PageClassifier 語義分類
    2. Stage 2 (昂貴 & 精準): Vision Parser + Financial Agent 只處理相關頁面
    """
    
    async def process(self, pdf_path: str, company_id: int, year: int):
        # 1. 解析 PDF → Markdown
        parser_output = await self._parse_pdf(pdf_path)
        
        # 2. 分類頁面 (找出財報相關頁面)
        relevant_pages = await self._classify_pages(parser_output)
        
        # 3. 提取結構化數據
        extracted_data = await self._extract_financial_data(relevant_pages)
        
        # 4. 驗證數據
        validation_result = await self._validate_data(extracted_data)
        
        # 5. 寫入數據庫
        await self._save_to_db(validation_result, company_id, year)
```

#### 批次處理
```python
# nanobot/ingestion/batch_processor.py
class BatchProcessor:
    """
    處理大批量 PDF 檔案的排程器
    """
    async def process_batch(self, pdf_paths: List[str]):
        # 使用 semaphore 控制並發數量
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        
        async def process_with_limit(path):
            async with semaphore:
                return await pipeline.process(path)
        
        tasks = [process_with_limit(path) for path in pdf_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return results
```

---

### 3. 結構化資料提取 (OpenDataLoader)

#### 解析核心
```python
# nanobot/ingestion/parsers/opendataloader_parser.py
class OpenDataLoaderParser:
    """
    OpenDataLoader 是一個強大的開源 PDF 解析器
    特點：
    - 精準解析表格 (Tables)
    - 保持正確的閱讀順序 (Reading order)
    - 輸出邊界框 (Bounding Boxes) 用於溯源
    """
    
    async def parse(self, pdf_path: str) -> ParsedDocument:
        from opendataloader import parse_pdf
        
        # 解析 PDF
        result = parse_pdf(pdf_path)
        
        # 轉換為內部格式
        return ParsedDocument(
            markdown=result.markdown,
            tables=result.tables,  # 結構化表格
            images=result.images,  # 圖片及其座標
            elements=[  # 所有元素及其邊界框
                {
                    "type": elem.type,      # text, table, image
                    "content": elem.content,
                    "bbox": elem.bbox,      # [x1, y1, x2, y2]
                    "page": elem.page_num
                }
                for elem in result.elements
            ]
        )
```

#### 視覺解析 (輔助)
```python
# nanobot/ingestion/parsers/vision_parser.py
class VisionParser:
    """
    使用 Vision LLM 處理複雜圖片和圖表
    """
    async def parse_chart(self, image_data: bytes) -> Dict:
        # 調用 Vision API (GPT-4V, Claude, etc.)
        response = await self.vision_client.chat(
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "data": image_data},
                    {"type": "text", "text": "Extract all data from this chart"}
                ]
            }]
        )
        
        return self._parse_response(response)
```

---

### 4. 數據清洗與資料庫存儲 (PostgreSQL)

#### 清洗與驗證
```python
# nanobot/ingestion/extractors/value_normalizer.py
class ValueNormalizer:
    """
    數值正規化：統一單位、貨幣、小數點
    """
    def normalize(self, value: str, context: Dict) -> NormalizedValue:
        # 移除逗號、百分比符號
        cleaned = re.sub(r'[,%]', '', value)
        
        # 解析數字
        num = float(cleaned)
        
        # 根據上下文轉換單位
        if context.get('unit') == 'million':
            num *= 1_000_000
        elif context.get('unit') == 'billion':
            num *= 1_000_000_000
        
        # 統一貨幣為 HKD
        if context.get('currency') == 'USD':
            num *= self._get_exchange_rate('USD', 'HKD')
        
        return NormalizedValue(value=num, currency='HKD', unit='base')
```

```python
# nanobot/ingestion/validators/math_rules.py
class MathValidator:
    """
    數學規則驗證：確保財報數字自洽
    """
    async def validate(self, data: FinancialData) -> ValidationResult:
        errors = []
        
        # 規則 1: 總計 = 各分項之和
        if data.revenue_breakdown:
            total = sum(item.amount for item in data.revenue_breakdown)
            if not is_close(total, data.total_revenue, tolerance=0.01):
                errors.append(f"Revenue breakdown sum mismatch: {total} vs {data.total_revenue}")
        
        # 規則 2: 資產 = 負債 + 權益
        if data.balance_sheet:
            if not is_close(data.assets, data.liabilities + data.equity):
                errors.append("Balance sheet doesn't balance")
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
```

#### 寫入 Postgres
```python
# nanobot/ingestion/repository/db_client.py
class DBClient:
    """
    數據庫客戶端 - 所有 SQL 操作集中在此
    """
    
    async def upsert_company(self, stock_code: str, **kwargs) -> int:
        """
        🎯 漸進式 Upsert：只填空值，不覆蓋已有數據
        """
        # 1. 查找現有公司
        existing = await self.get_company_by_stock_code(stock_code)
        
        if existing:
            # 2. 按需更新（只更新空值欄位）
            update_fields = {}
            if kwargs.get('name_en') and not existing.get('name_en'):
                update_fields['name_en'] = kwargs['name_en']
            if kwargs.get('industry') and not existing.get('industry'):
                update_fields['industry'] = kwargs['industry']
            
            if update_fields:
                await self.update_company(existing['id'], update_fields)
                return existing['id']
        else:
            # 3. 創建新公司
            return await self.insert_company(kwargs)
    
    async def insert_financial_metrics(self, metrics: List[Metric]):
        """
        批量插入財務指標（使用事務）
        """
        async with self.conn.transaction():
            await self.conn.executemany(
                """
                INSERT INTO financial_metrics 
                (company_id, year, metric_name, value, unit, category)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                [(m.company_id, m.year, m.name, m.value, m.unit, m.category) 
                 for m in metrics]
            )
```

---

### 5. 自然語言查詢轉換 (Vanna AI)

#### 模型訓練與同步
```python
# vanna-service/vanna_training.py
class VannaTrainingData:
    """
    Vanna 訓練資料管理器
    特點：
    - 從 JSON 檔案載入訓練資料（資料與代碼分離）
    - DDL 白名單驗證（防止 Vanna 學到垃圾表）
    - 支援熱更新（更新 JSON 後重新訓練）
    """
    
    async def train_vanna(self, vanna_instance, force: bool = False):
        if not force and vanna_instance._trained:
            return {'status': 'skipped'}
        
        # 1. 訓練 DDL (資料庫結構)
        ddl_statements = self.load_ddl()  # 從 data/ddl.json 載入
        for ddl in ddl_statements:
            vanna_instance.train(ddl=ddl)
        
        # 2. 訓練文檔 (欄位說明)
        docs = self.load_documentation()  # 從 data/documentation.json 載入
        for doc in docs:
            vanna_instance.train(documentation=doc)
        
        # 3. 訓練示例查詢 (問題-SQL 配對)
        sql_pairs = self.load_sql_pairs()  # 從 data/sql_pairs.json 載入
        for pair in sql_pairs:
            vanna_instance.train(question=pair['question'], sql=pair['sql'])
        
        vanna_instance._trained = True
        return {'status': 'trained'}
```

#### 用戶提問流程
```python
# nanobot/agent/tools/vanna_tool.py
class VannaSQL:
    """
    Vanna AI Text-to-SQL 生成器
    """
    
    async def query(self, question: str) -> QueryResult:
        # 1. 確保已訓練
        if not self._trained:
            await self.train_schema()
        
        # 2. 生成 SQL
        sql = self.vn.generate_sql(question)
        
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
            explanation=self._explain_query(sql, results)
        )
```

---

## 💡 優化建議與實現方案

### 1. 非同步處理與前端進度反饋 (Asynchronous Processing)

#### 痛點
PDF 解析（特別是包含 OCR 時）非常耗時，同步 HTTP 請求容易 Timeout。

#### 實現方案

**後端：任務隊列**
```python
# nanobot/bus/queue.py
class MessageBus:
    def __init__(self):
        self._task_status = {}  # task_id -> status
    
    async def publish_processing_task(self, pdf_path: str) -> str:
        task_id = str(uuid.uuid4())
        self._task_status[task_id] = {
            'status': 'queued',
            'progress': 0,
            'created_at': datetime.now()
        }
        
        # 發布到背景任務隊列
        asyncio.create_task(self._process_with_status(task_id, pdf_path))
        
        return task_id
    
    async def _process_with_status(self, task_id: str, pdf_path: str):
        try:
            self._update_status(task_id, 'processing', progress=10)
            
            # 解析階段
            await self._parse_pdf(pdf_path)
            self._update_status(task_id, 'processing', progress=40)
            
            # 提取階段
            await self._extract_data()
            self._update_status(task_id, 'processing', progress=70)
            
            # 入庫階段
            await self._save_to_db()
            self._update_status(task_id, 'completed', progress=100)
            
        except Exception as e:
            self._update_status(task_id, 'failed', error=str(e))
    
    def _update_status(self, task_id: str, status: str, progress: int = None, error: str = None):
        self._task_status[task_id].update({
            'status': status,
            'progress': progress or self._task_status[task_id]['progress'],
            'error': error,
            'updated_at': datetime.now()
        })
    
    def get_task_status(self, task_id: str) -> Dict:
        return self._task_status.get(task_id, {'status': 'not_found'})
```

**API 端點**
```python
# webui/app/api/document.py
@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """上傳文件，立即返回 task_id"""
    task_id = await pdf_service.queue_processing(file)
    return {"task_id": task_id, "status": "queued"}

@app.get("/api/documents/status/{task_id}")
async def get_document_status(task_id: str):
    """輪詢任務狀態"""
    status = await pdf_service.get_task_status(task_id)
    return status
```

**前端：輪詢進度**
```javascript
// webui/static/ui.js
async function uploadPDF(file) {
    // 1. 上傳文件
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch('/api/documents/upload', {
        method: 'POST',
        body: formData
    });
    
    const { task_id } = await response.json();
    
    // 2. 開始輪詢狀態
    pollTaskStatus(task_id);
}

async function pollTaskStatus(task_id) {
    const progressInterval = setInterval(async () => {
        const response = await fetch(`/api/documents/status/${task_id}`);
        const status = await response.json();
        
        // 更新進度條
        updateProgressBar(status.progress);
        updateStatusText(status.status);
        
        if (status.status === 'completed' || status.status === 'failed') {
            clearInterval(progressInterval);
            if (status.status === 'completed') {
                showSuccess('處理完成！');
                refreshDocumentList();
            } else {
                showError(`處理失敗：${status.error}`);
            }
        }
    }, 1000); // 每秒輪詢一次
}
```

---

### 2. 混合 RAG 架構：Text-to-SQL + 向量搜尋 (Hybrid Routing)

#### 痛點
Vanna 擅長表格查詢，但不擅長純文字語意理解。

#### 實現方案

**數據存儲：同時存儲結構化和向量**
```python
# nanobot/ingestion/pipeline.py
class DocumentPipeline:
    async def _save_to_db(self, data, company_id, year):
        # 1. 結構化數據 → PostgreSQL (現有流程)
        await self.db.insert_financial_metrics(data.metrics)
        await self.db.insert_revenue_breakdown(data.revenue_breakdown)
        
        # 2. 純文字 → Vector Store (新增)
        await self._save_to_vector_store(data.text_chunks, company_id, year)
    
    async def _save_to_vector_store(self, chunks: List[TextChunk], company_id: int, year: int):
        """
        將文字分塊並向量化存儲
        """
        from langchain.vectorstores import PGVector
        from langchain.embeddings import OpenAIEmbeddings
        
        # 初始化向量存儲（使用 pgvector）
        vector_store = PGVector(
            connection_string=self.db_url,
            embedding_function=OpenAIEmbeddings(),
            collection_name=f"company_{company_id}_{year}"
        )
        
        # 添加元數據
        documents = [
            Document(
                page_content=chunk.text,
                metadata={
                    "company_id": company_id,
                    "year": year,
                    "page": chunk.page,
                    "section": chunk.section
                }
            )
            for chunk in chunks
        ]
        
        # 批量插入
        await vector_store.aadd_documents(documents)
```

**路由機制：判斷問題類型**
```python
# nanobot/agent/tools/hybrid_router.py
class HybridRouter:
    """
    智能路由：判斷問題類型並選擇合適的查詢方式
    """
    
    async def route(self, question: str) -> QueryResult:
        # 1. 使用 LLM 判斷問題類型
        intent = await self._classify_intent(question)
        
        if intent == 'structured_query':
            # 表格查詢：走 Vanna -> SQL
            return await self._query_with_vanna(question)
        elif intent == 'semantic_search':
            # 語意搜尋：走 Vector Search
            return await self._query_with_vector(question)
        else:
            # 混合查詢：兩者都執行
            sql_result = await self._query_with_vanna(question)
            vector_result = await self._query_with_vector(question)
            return self._merge_results(sql_result, vector_result)
    
    async def _classify_intent(self, question: str) -> str:
        """
        分類問題意圖
        """
        # 關鍵詞匹配 + LLM 分類
        structured_keywords = ['多少', '百分比', '總計', '比較', 'top', '排名']
        semantic_keywords = ['為什麼', '如何', '說明', '分析', '結論']
        
        if any(kw in question.lower() for kw in structured_keywords):
            return 'structured_query'
        elif any(kw in question.lower() for kw in semantic_keywords):
            return 'semantic_search'
        else:
            # 使用 LLM 進一步判斷
            response = await self.llm.chat(
                f"Classify this question as 'structured_query' or 'semantic_search': {question}"
            )
            return response.content.strip()
    
    async def _query_with_vanna(self, question: str) -> QueryResult:
        """使用 Vanna 進行 Text-to-SQL 查詢"""
        sql = self.vanna.generate_sql(question)
        data = await self.db.execute(sql)
        return QueryResult(source='sql', data=data, sql=sql)
    
    async def _query_with_vector(self, question: str) -> QueryResult:
        """使用向量搜尋進行語意查詢"""
        results = await self.vector_store.asimilarity_search(question, k=5)
        return QueryResult(source='vector', data=results)
```

**配置示例**
```yaml
# config.json
{
    "rag": {
        "hybrid_enabled": true,
        "vector_store": {
            "type": "pgvector",
            "connection_string": "${DATABASE_URL}",
            "embedding_model": "text-embedding-3-small"
        },
        "router": {
            "use_llm_classification": true,
            "fallback_to_hybrid": true
        }
    }
}
```

---

### 3. 利用 Bounding Boxes 實作「精準溯源 (Citation)」

#### 優勢最大化
OpenDataLoader 返回的邊界框可以用於高亮顯示原始 PDF 內容。

#### 實現方案

**數據存儲：保留座標信息**
```python
# nanobot/ingestion/repository/db_client.py
class DBClient:
    async def insert_document_pages(self, pages: List[DocumentPage]):
        """
        存儲頁面內容及其元素座標
        """
        await self.conn.executemany(
            """
            INSERT INTO document_pages 
            (company_id, year, page_num, markdown_content, elements_json)
            VALUES ($1, $2, $3, $4, $5)
            """,
            [
                (
                    p.company_id,
                    p.year,
                    p.page_num,
                    p.markdown_content,
                    json.dumps([  # 存儲所有元素及其座標
                        {
                            "type": e.type,
                            "content": e.content,
                            "bbox": e.bbox  # [x1, y1, x2, y2]
                        }
                        for e in p.elements
                    ])
                )
                for p in pages
            ]
        )
```

**查詢結果：附加溯源信息**
```python
# nanobot/agent/tools/vanna_tool.py
class VannaSQL:
    async def query_with_citation(self, question: str) -> QueryResult:
        # 1. 執行 SQL 查詢
        sql = self.vn.generate_sql(question)
        results = await self._execute_sql(sql)
        
        # 2. 為每個結果查找來源頁面
        cited_results = []
        for row in results:
            citation = await self._find_citation(row)
            cited_results.append({
                **row,
                "_citation": {
                    "page": citation.page,
                    "bbox": citation.bbox,  # 用於高亮
                    "source_file": citation.source_file
                }
            })
        
        return QueryResult(data=cited_results, has_citation=True)
    
    async def _find_citation(self, row: Dict) -> Citation:
        """
        根據數據查找原始 PDF 頁面和座標
        """
        # 從 document_pages 表中查找匹配的段落
        result = await self.conn.fetchrow(
            """
            SELECT page_num, elements_json, source_file
            FROM document_pages
            WHERE company_id = $1 AND year = $2
            AND elements_json::text LIKE $3
            LIMIT 1
            """,
            row['company_id'],
            row['year'],
            f"%{row['metric_name']}%"
        )
        
        # 解析元素找到具體座標
        elements = json.loads(result['elements_json'])
        target_element = next(
            (e for e in elements if row['value'] in str(e['content'])),
            None
        )
        
        return Citation(
            page=result['page_num'],
            bbox=target_element['bbox'] if target_element else None,
            source_file=result['source_file']
        )
```

**前端：PDF 預覽與高亮**
```javascript
// webui/static/ui.js
class PDFViewer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.pdf = null;
        this.highlights = [];
    }
    
    async loadPDF(pdfPath) {
        this.pdf = await pdfjsLib.getDocument(pdfPath).promise;
        this.render();
    }
    
    highlightBbox(pageNum, bbox) {
        // bbox: [x1, y1, x2, y2]
        const page = await this.pdf.getPage(pageNum);
        const viewport = page.getViewport({ scale: 1.5 });
        
        // 轉換座標（PDF 座標系原點在左下角）
        const x = bbox[0];
        const y = viewport.height - bbox[3];  // 翻轉 Y 軸
        const width = bbox[2] - bbox[0];
        const height = bbox[3] - bbox[1];
        
        // 創建高亮層
        const highlight = document.createElement('div');
        highlight.style.position = 'absolute';
        highlight.style.left = `${x}px`;
        highlight.style.top = `${y}px`;
        highlight.style.width = `${width}px`;
        highlight.style.height = `${height}px`;
        highlight.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
        highlight.style.border = '2px solid yellow';
        
        this.container.appendChild(highlight);
        this.highlights.push(highlight);
    }
    
    clearHighlights() {
        this.highlights.forEach(h => h.remove());
        this.highlights = [];
    }
}

// 使用示例
async function showAnswerWithCitation(answer) {
    // 顯示答案
    displayAnswer(answer.text);
    
    // 如果有溯源信息，高亮 PDF
    if (answer.citation) {
        const viewer = new PDFViewer('pdf-container');
        await viewer.loadPDF(answer.citation.source_file);
        viewer.highlightBbox(answer.citation.page, answer.citation.bbox);
        
        // 點擊答案時滾動到 PDF
        document.querySelector('.answer').onclick = () => {
            document.getElementById('pdf-container').scrollIntoView();
        };
    }
}
```

---

### 4. Vanna Schema 的動態更新機制 (Dynamic Schema Updating)

#### 痛點
新 PDF 可能產生新的 Table 或欄位，Vanna 需要保持對資料庫結構的最新認知。

#### 實現方案

**事件驅動：自動觸發訓練**
```python
# nanobot/bus/events.py
class EventBus:
    """
    事件總線：模組間解耦通信
    """
    
    def __init__(self):
        self._subscribers = {}
    
    def subscribe(self, event_type: str, callback):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
    
    async def publish(self, event_type: str, data: Dict):
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                await callback(data)

# 訂閱事件
event_bus.subscribe('schema_updated', vanna_service.retrain)
```

**自動重訓邏輯**
```python
# vanna-service/vanna_training.py
class VannaService:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.event_bus.subscribe('schema_updated', self.on_schema_updated)
    
    async def on_schema_updated(self, data: Dict):
        """
        監聽資料庫結構變更事件，自動重訓
        """
        logger.info(f"📢 收到 schema_updated 事件：{data}")
        
        # 1. 檢查是否有新表或欄位
        changes = await self._detect_schema_changes(data)
        
        if changes.has_changes:
            # 2. 更新 DDL 訓練資料
            await self._update_ddl_training(changes.new_tables)
            
            # 3. 重新訓練 Vanna
            await self.train_vanna(force=True)
            
            # 4. 發布訓練完成事件
            await self.event_bus.publish('vanna_retrained', {
                'timestamp': datetime.now(),
                'changes': changes
            })
            
            logger.info("✅ Vanna 已自動重訓")
    
    async def _detect_schema_changes(self, data: Dict) -> SchemaChanges:
        """
        檢測資料庫結構變更
        """
        # 查詢當前資料庫結構
        current_tables = await self.db.fetch_tables()
        current_columns = await self.db.fetch_columns()
        
        # 與 cached schema 比較
        cached_tables = self._cached_schema.get('tables', [])
        cached_columns = self._cached_schema.get('columns', [])
        
        new_tables = set(current_tables) - set(cached_tables)
        new_columns = set(current_columns) - set(cached_columns)
        
        # 更新 cache
        self._cached_schema = {
            'tables': current_tables,
            'columns': current_columns
        }
        
        return SchemaChanges(
            has_changes=bool(new_tables or new_columns),
            new_tables=new_tables,
            new_columns=new_columns
        )
```

**觸發事件：數據入庫後通知**
```python
# nanobot/ingestion/pipeline.py
class DocumentPipeline:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
    
    async def _save_to_db(self, data, company_id, year):
        # 1. 插入數據
        await self.db.insert_financial_metrics(data.metrics)
        
        # 2. 檢查是否有新欄位
        schema_changed = await self._check_schema_changed(data.metrics)
        
        if schema_changed:
            # 3. 發布事件
            await self.event_bus.publish('schema_updated', {
                'company_id': company_id,
                'year': year,
                'new_fields': data.metrics[0].keys() if data.metrics else []
            })
```

**配置：控制重訓頻率**
```yaml
# config.json
{
    "vanna": {
        "auto_retrain": true,
        "retrain_threshold": {
            "min_new_columns": 1,      # 至少 1 個新欄位才重訓
            "cooldown_minutes": 30     # 冷卻時間（避免頻繁重訓）
        },
        "training_data": {
            "ddl_path": "vanna-service/data/ddl.json",
            "sql_pairs_path": "vanna-service/data/sql_pairs.json",
            "auto_update_ddl": true    # 自動從 DB 更新 DDL
        }
    }
}
```

---

## 📋 檢查清單 (Checklist)

### 基礎功能
- [ ] PDF 上傳與驗證
- [ ] OpenDataLoader 解析
- [ ] 數據庫存儲
- [ ] Vanna Text-to-SQL 查詢

### 優化功能
- [ ] 非同步處理與進度反饋
- [ ] 混合 RAG 路由（SQL + Vector）
- [ ] PDF 溯源高亮
- [ ] Vanna 自動重訓

### 監控與日誌
- [ ] 處理時長監控
- [ ] 錯誤率統計
- [ ] 用戶查詢日誌
- [ ] Vanna 訓練記錄

---

## 🔗 相關文檔

- [Server Startup Workflow](./server-startup-workflow.md) - 服務器啟動流程
- [Vanna Training Guide](./vanna-training.md) - Vanna 訓練指南
- [Database Schema](./database-schema.md) - 數據庫結構說明

---

## 📝 版本歷史

| 版本 | 日期 | 變更 |
|------|------|------|
| 1.0 | 2026-04-10 | 初始版本 |
