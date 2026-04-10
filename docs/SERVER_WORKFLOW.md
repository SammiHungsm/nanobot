# 服务器启动 Workflow 完整文档

## 📊 架构概览

### 服务架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Compose 编排                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │  postgres-financial  │    │   vanna-service    │                  │
│  │  (PostgreSQL 16) │◄───│  (Text-to-SQL)    │                  │
│  │  Port: 5433      │    │  Port: 8000       │                  │
│  └────────┬─────────┘    └────────┬──────────┘                  │
│           │                       │                              │
│           │                       │                              │
│           ▼                       ▼                              │
│  ┌──────────────────────────────────────────┐                   │
│  │        nanobot-gateway                   │                   │
│  │   (主 AI 服務 - LLM + Tool Calling)      │                   │
│  │   Port: 18790 (Gateway) / 8081 (HTTP)    │                   │
│  └────────┬─────────────────────────────────┘                   │
│           │                                                       │
│           │ HTTP API                                              │
│           ▼                                                       │
│  ┌──────────────────────────────────────────┐                   │
│  │        nanobot-webui                     │                   │
│  │   (FastAPI 前端 + PDF 處理)              │                   │
│  │   Port: 3000                             │                   │
│  └──────────────────────────────────────────┘                   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 服务启动流程

### 阶段 1：基础设施启动

#### 1.1 PostgreSQL 数据库

**启动命令**：
```bash
docker-compose up -d postgres-financial
```

**启动流程**：
1. 加载 `pgvector/pgvector:pg16` 镜像
2. 初始化数据库：`annual_reports`
3. 执行 Schema 初始化脚本：`storage/init_complete.sql`
4. 启用 `vector` 扩展（用于 embeddings）
5. 健康检查：`pg_isready -U postgres`

**关键文件**：
- [docker-compose.yml](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/docker-compose.yml) (L12-34)
- [init_complete.sql](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/storage/init_complete.sql)

**依赖条件**：
```yaml
depends_on:
  postgres-financial:
    condition: service_healthy
```

---

### 阶段 2：核心服务启动

#### 2.1 Vanna Service（Text-to-SQL）

**启动命令**：
```bash
docker-compose up -d vanna-service
```

**启动流程**：
1. **初始化 Vanna AI**
   ```python
   # vanna-service/start.py (L38-56)
   class MyVanna(ChromaDB_VectorStore, OpenAI_Chat):
       def __init__(self, config=None):
           # ChromaDB 配置
           chroma_config = {'path': config.get('path')}
           # OpenAI 配置
           openai_config = {k: v for k, v in config.items() if k != 'path'}
           
           ChromaDB_VectorStore.__init__(self, config=chroma_config)
           OpenAI_Chat.__init__(self, config=openai_config)
   ```

2. **连接 PostgreSQL**
   ```python
   # vanna-service/start.py (L216-227)
   db_url = os.getenv("DATABASE_URL")
   vn.connect_to_postgres(db_url)
   ```

3. **训练 Vanna**
   ```python
   # vanna-service/start.py (L300-350)
   def train_vanna_with_enhanced_data():
       # 从 JSON 加载训练数据
       trainer = VannaTrainingData(data_dir="/app/data")
       stats = trainer.train_vanna(vn, validate=True)
       
       # 训练内容：
       # - DDL (CREATE TABLE statements)
       # - Documentation (使用规则)
       # - SQL Pairs (问答示例)
   ```

4. **启动 FastAPI**
   ```python
   # vanna-service/start.py (L800+)
   uvicorn.run(app, host="0.0.0.0", port=8000)
   ```

**关键文件**：
- [start.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/vanna-service/start.py)
- [vanna_training.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/vanna-service/vanna_training.py)
- [data/documentation.json](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/vanna-service/data/documentation.json)

**环境变量**：
```bash
DATABASE_URL=postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports
VANNA_MODEL=financial-sql
LOG_LEVEL=DEBUG
```

---

#### 2.2 Nanobot Gateway（主 AI 服务）

**启动命令**：
```bash
docker-compose up -d nanobot-gateway
```

**启动流程**：
1. **加载配置**
   ```python
   # nanobot/__main__.py
   from nanobot.cli.commands import app
   app()  # Typer CLI 应用
   ```

2. **初始化 Gateway**
   ```python
   # nanobot/cli/commands.py (L800+)
   @app.command()
   def gateway(config: str = None):
       # 加载配置
       cfg = Config.load(config)
       
       # 启动 Gateway 服务
       from nanobot.gateway import start_gateway
       start_gateway(cfg)
   ```

3. **注册 Tools**
   ```python
   # nanobot/agent/tools/registry.py
   registry = ToolRegistry()
   registry.register(upsert_metric_tool)
   registry.register(update_company_attribute_tool)
   # ... 其他工具
   ```

4. **启动 HTTP 服务**
   ```
   Port 18790: Gateway 内部通信
   Port 8081: HTTP API
   ```

**关键文件**：
- [__main__.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/nanobot/__main__.py)
- [commands.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/nanobot/cli/commands.py)
- [registry.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/nanobot/agent/tools/registry.py)

**环境变量**：
```bash
DATABASE_URL=postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports
NANOBOT_CONFIG=/app/config/config.json
LOG_LEVEL=DEBUG
```

---

#### 2.3 Nanobot WebUI（前端 + PDF 处理）

**启动命令**：
```bash
docker-compose up -d nanobot-webui
```

**启动流程**：
1. **初始化 FastAPI**
   ```python
   # webui/app/main.py (L21-35)
   app = FastAPI(
       title="Nanobot Financial Chat",
       version="2.0.0"
   )
   
   # 配置 CORS
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["*"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```

2. **初始化目录**
   ```python
   # webui/app/main.py (L38-43)
   UPLOAD_DIR = Path(os.getenv("PDF_UPLOAD_DIR", "./uploads"))
   OUTPUT_DIR = Path(os.getenv("PDF_OUTPUT_DIR", "./outputs"))
   
   UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
   OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
   ```

3. **初始化 DocumentService**
   ```python
   # webui/app/main.py (L46)
   init_document_service(UPLOAD_DIR, OUTPUT_DIR)
   
   # webui/app/api/document.py (L18-22)
   def init_document_service(upload_dir: Path, output_dir: Path):
       global document_service
       document_service = DocumentService(upload_dir, output_dir)
   ```

4. **初始化 DocumentPipeline**
   ```python
   # webui/app/services/document_service.py (L28-35)
   class DocumentService:
       def __init__(self, upload_dir: Path, output_dir: Path):
           # 🎯 关键：初始化 Pipeline
           self.pipeline = DocumentPipeline(
               db_url=db_url,
               data_dir=data_dir,
               use_opendataloader=True
           )
   ```

5. **注册路由**
   ```python
   # webui/app/main.py (L49-50)
   app.include_router(chat_router)
   app.include_router(document_router)
   ```

6. **挂载静态文件**
   ```python
   # webui/app/main.py (L48)
   app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
   ```

7. **启动 Uvicorn**
   ```python
   # webui/app/main.py (L85-86)
   uvicorn.run(app, host="0.0.0.0", port=8080)
   ```

**关键文件**：
- [main.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/app/main.py)
- [document_service.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/app/services/document_service.py)
- [document.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/app/api/document.py)
- [chat.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/app/api/chat.py)

**环境变量**：
```bash
PDF_UPLOAD_DIR=/app/uploads
PDF_OUTPUT_DIR=/app/outputs
DATABASE_URL=postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports
GATEWAY_URL=http://nanobot-gateway:8081
DATA_DIR=/app/data/raw
NANOBOT_CONFIG=/app/config/config.json
JAVA_OPTS=-Xmx2g -Xms512m  # OpenDataLoader 内存配置
```

---

## 📦 核心数据流

### 数据流 1：PDF 上传与处理

```
用户上传 PDF
    ↓
WebUI (/api/upload)
    ↓
DocumentService.add_document()
    ├── 生成 doc_id
    ├── 存储文件到 /app/uploads
    └── 加入处理队列
    ↓
DocumentService.process_queue() [后台任务]
    ↓
DocumentPipeline.process_pdf_full()
    ├── OpenDataLoader 解析 PDF
    ├── Vision LLM 提取封面信息
    ├── EntityResolver 标准化名称
    ├── ValueNormalizer 标准化数值
    └── DBClient 写入数据库
        ├── companies (Upsert)
        ├── financial_metrics (EAV)
        ├── revenue_breakdown
        └── companies.extra_data (JSONB)
    ↓
更新文档状态
```

**代码参考**：
```python
# webui/app/services/document_service.py (L100-150)
async def process_queue(self):
    while True:
        doc_id = await self.processing_queue.get()
        doc = self.documents_db[doc_id]
        
        # 显式分流
        if doc["doc_type"] == "index_report":
            # 路线 A：恒指主数据更新
            result = await self._process_master_index_report(doc["path"])
        else:
            # 路线 B：一般公司年报
            result = await self._process_with_pipeline(doc, update_progress)
```

---

### 数据流 2：用户查询

```
用户输入问题
    ↓
WebUI (/api/chat)
    ↓
Gateway (/api/chat)
    ↓
Nanobot Agent (LLM)
    ├── 判断意图
    │   ├── 财务数据查询 → 调用 Vanna
    │   ├── 文档搜索 → 搜索 document_pages
    │   └── 一般对话 → 直接回复
    └── Tool Calling
        ├── query_financial_database
        ├── search_documents
        └── resolve_entity
    ↓
Vanna Service (Text-to-SQL)
    ├── 生成 SQL
    ├── 执行查询
    └── 返回结果
    ↓
Agent 整理答案
    ↓
返回用户
```

**代码参考**：
```python
# webui/app/api/chat.py (L12-30)
@router.post("", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{GATEWAY_URL}/api/chat",
            json={
                "message": request.message,
                "username": request.username,
                "document_path": request.document_path
            }
        )
        return ChatResponse(reply=result.get("reply", ""))
```

---

## 🛠️ 关键代码检查与修复

### ✅ 修复 1：DocumentPipeline 异步初始化（已修复）

**问题**：`DocumentPipeline` 需要异步连接数据库，但在 `DocumentService.__init__` 中同步初始化。

**修复方案**：
```python
# webui/app/services/document_service.py
class DocumentService:
    def __init__(self, upload_dir: Path, output_dir: Path):
        # 🎯 延迟初始化 Pipeline
        self.pipeline = None
        self._pipeline_connected = False
    
    async def _ensure_pipeline_connected(self):
        """确保 Pipeline 已连接数据库"""
        if not self._pipeline_connected:
            self.pipeline = DocumentPipeline(...)
            await self.pipeline.connect()
            self._pipeline_connected = True
    
    async def _process_with_pipeline(self, doc: dict, update_progress):
        # 🎯 在处理前确保连接
        await self._ensure_pipeline_connected()
        result = await self.pipeline.process_pdf_full(...)
```

**影响**：避免了首次 PDF 处理时的数据库连接失败问题。

---

### ✅ 修复 2：Vanna Service 健康检查（已修复）

**问题**：Vanna Service 启动时依赖 PostgreSQL，但没有等待 PostgreSQL 完全就绪。

**修复方案**：
```yaml
# docker-compose.yml
vanna-service:
  depends_on:
    postgres-financial:
      condition: service_healthy  # ✅ 等待健康检查通过
```

**影响**：避免了 Vanna 在 PostgreSQL 未准备好时尝试连接导致的启动失败。

---

### ✅ 修复 3：环境变量一致性（已修复）

**问题**：`GATEWAY_URL` 硬编码为 Docker 服务名，本地开发会失败。

**修复方案**：
```python
# webui/app/api/chat.py
_default_gateway = (
    "http://localhost:8081" 
    if os.getenv("ENV") == "development" or not os.getenv("GATEWAY_URL")
    else "http://nanobot-gateway:8081"
)
GATEWAY_URL = os.getenv("GATEWAY_URL", _default_gateway)
```

**影响**：支持本地开发（ENV=development）和 Docker 环境的无缝切换。

---

### ✅ 修复 4：错误处理完善（已修复）

**问题**：错误处理缺少详细的 traceback 信息，且未处理 `CancelledError`。

**修复方案**：
```python
# webui/app/services/document_service.py
except Exception as e:
    import traceback
    doc["status"] = "failed"
    doc["error_message"] = str(e)
    doc["traceback"] = traceback.format_exc()
    logger.error(f"处理失败: {e}", exc_info=True)

except asyncio.CancelledError:
    logger.warning("Processing queue cancelled")
    break
```

**影响**：提供完整的错误追踪能力，便于问题排查。

---

## 📋 验证结果

运行 [verify_code_fixes.py](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/verify_code_fixes.py) 验证：

```
[PASS] 修复 1: Pipeline 异步初始化
[PASS] 修复 2: Vanna 健康检查
[PASS] 修复 3: 环境变量一致性
[PASS] 修复 4: 错误处理完善

通过修复: 4/4
安全度: 100.0%
```

---

## 📋 服务健康检查

### PostgreSQL

```bash
# 检查数据库连接
docker exec -it postgres-financial psql -U postgres -d annual_reports -c "SELECT 1;"

# 检查表结构
docker exec -it postgres-financial psql -U postgres -d annual_reports -c "\dt"

# 检查扩展
docker exec -it postgres-financial psql -U postgres -d annual_reports -c "SELECT * FROM pg_extension;"
```

### Vanna Service

```bash
# 检查 Vanna 健康状态
curl http://localhost:8000/health

# 测试 SQL 生成
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "列出所有公司"}'
```

### Gateway

```bash
# 检查 Gateway 状态
curl http://localhost:8081/health

# 测试聊天
curl -X POST http://localhost:8081/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'
```

### WebUI

```bash
# 检查 WebUI 状态
curl http://localhost:3000/health

# 检查文档列表
curl http://localhost:3000/api/documents
```

---

## 🔧 常见问题排查

### 问题 1：PDF 处理卡住

**症状**：上传 PDF 后，状态一直显示 "processing"。

**排查步骤**：
1. 检查后台队列：
   ```python
   # 进入 WebUI 容器
   docker exec -it nanobot-webui python
   
   # 检查队列状态
   from app.api import document_service
   print(document_service.documents_db)
   print(document_service.processing_queue.qsize())
   ```

2. 检查 Pipeline 连接：
   ```python
   # 检查数据库连接
   await document_service.pipeline.db_client.conn.fetchval("SELECT 1")
   ```

3. 检查内存使用：
   ```bash
   docker stats nanobot-webui
   ```

---

### 问题 2：Vanna 生成 SQL 错误

**症状**：Vanna 生成的 SQL 无法执行或结果错误。

**排查步骤**：
1. 检查训练状态：
   ```bash
   curl http://localhost:8000/status
   ```

2. 重新训练 Vanna：
   ```bash
   curl -X POST http://localhost:8000/train \
     -H "Content-Type: application/json" \
     -d '{"train_type": "schema"}'
   ```

3. 检查训练数据：
   ```bash
   docker exec -it vanna-service ls -la /app/data
   docker exec -it vanna-service cat /app/data/documentation.json | jq .
   ```

---

### 问题 3：Gateway 连接失败

**症状**：WebUI 返回 503 错误，无法连接 AI 引擎。

**排查步骤**：
1. 检查 Gateway 服务状态：
   ```bash
   docker-compose ps nanobot-gateway
   docker logs nanobot-gateway --tail 100
   ```

2. 检查网络连接：
   ```bash
   # 从 WebUI 容器测试连接
   docker exec -it nanobot-webui curl http://nanobot-gateway:8081/health
   ```

3. 检查配置文件：
   ```bash
   docker exec -it nanobot-gateway cat /app/config/config.json | jq .
   ```

---

## 📝 启动脚本

### 完整启动脚本

```bash
#!/bin/bash
# start.sh - 完整启动脚本

echo "🚀 启动 SFC AI 财报分析系统..."

# 1. 启动基础设施
echo "📦 启动 PostgreSQL..."
docker-compose up -d postgres-financial

# 等待 PostgreSQL 就绪
echo "⏳ 等待 PostgreSQL 启动..."
until docker-compose exec postgres-financial pg_isready -U postgres; do
  sleep 1
done
echo "✅ PostgreSQL 已就绪"

# 2. 启动 Vanna Service
echo "🤖 启动 Vanna Service..."
docker-compose up -d vanna-service

# 等待 Vanna 初始化
echo "⏳ 等待 Vanna 训练完成..."
sleep 10

# 3. 启动 Gateway
echo "🎯 启动 Nanobot Gateway..."
docker-compose up -d nanobot-gateway

# 4. 启动 WebUI
echo "🌐 启动 WebUI..."
docker-compose up -d nanobot-webui

# 5. 检查服务状态
echo "🔍 检查服务状态..."
docker-compose ps

echo "✅ 系统启动完成！"
echo ""
echo "🌐 WebUI: http://localhost:3000"
echo "🤖 Gateway API: http://localhost:8081"
echo "📊 Vanna API: http://localhost:8000"
echo "🗄️ PostgreSQL: localhost:5433"
```

### 健康检查脚本

```bash
#!/bin/bash
# health_check.sh - 服务健康检查

echo "🔍 检查服务健康状态..."

# PostgreSQL
echo "📦 PostgreSQL:"
docker-compose exec postgres-financial pg_isready -U postgres

# Vanna Service
echo "🤖 Vanna Service:"
curl -s http://localhost:8000/health | jq .

# Gateway
echo "🎯 Gateway:"
curl -s http://localhost:8081/health | jq .

# WebUI
echo "🌐 WebUI:"
curl -s http://localhost:3000/health | jq .

echo "✅ 健康检查完成"
```

---

## 📚 相关文档

- [架构总结 v3.0](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/ARCHITECTURE_V3_SUMMARY.md)
- [Fact-Check 验证](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/fact_check_lethal_risks.py)
- [API 文档](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/static/index.html)
- [配置文件](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/config/config.json)

---

## 📞 支持

如遇问题，请检查：
1. Docker 日志：`docker-compose logs [service-name]`
2. 健康检查：`./health_check.sh`
3. 环境变量：`docker-compose config`
4. 网络连接：`docker network inspect nanobot_default`