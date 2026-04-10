# Nanobot Server Startup Workflow

## 概述

本文檔詳細說明 Nanobot 服務器啟動時的工作流程，包括組件初始化、依賴關係和數據流。

---

## 1. 啟動入口點

### 1.1 CLI 命令 (`nanobot/cli/commands.py`)

服務器有兩種啟動模式：

#### 模式 A: API Server (`nanobot serve`)
```python
@app.command()
def serve(...):
    """Start the OpenAI-compatible API server (/v1/chat/completions)."""
```
- **用途**: 提供 OpenAI 兼容的 HTTP API
- **端點**: `/v1/chat/completions`, `/v1/models`, `/health`
- **會話**: 單一持久化會話 (`api:default`)

#### 模式 B: Gateway Server (`nanobot gateway`)
```python
@app.command()
def gateway(...):
    """Start the nanobot gateway."""
```
- **用途**: 多通道網關（Telegram, WhatsApp, Slack 等）
- **功能**: 包含 Cron 服務、心跳服務、通道管理

---

## 2. 啟動流程圖

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI Entry Point                          │
│              (nanobot/cli/commands.py)                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Load Runtime Config                                     │
│     _load_runtime_config()                                  │
│     - 讀取 config.json                                      │
│     - 解析環境變數 ${VAR}                                   │
│     - 驗證配置                                              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Create Provider                                         │
│     _make_provider()                                        │
│     - 根據 model 選擇 backend                               │
│     - 初始化 LLM Provider (OpenAI/Azure/Anthropic)          │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Initialize Core Components                              │
│     - MessageBus()          # 內部消息隊列                  │
│     - SessionManager()      # 會話管理                      │
│     - CronService()         # 定時任務 (gateway 模式)       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Create AgentLoop                                        │
│     AgentLoop(...)                                          │
│     - 註冊默認工具 (Filesystem, Search, Web, etc.)          │
│     - 初始化 SubagentManager                                │
│     - 初始化 Consolidator (會話壓縮)                        │
│     - 初始化 Dream (記憶鞏固)                               │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Create Web Application                                  │
│     - API 模式：create_app(agent_loop)                      │
│     - Gateway 模式：ChannelManager + HTTP server            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Startup Hooks                                           │
│     - on_startup: agent_loop._connect_mcp()                 │
│     - 連接 MCP 服務器                                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  7. Run Event Loop                                          │
│     - aiohttp.web.run_app()                                 │
│     - agent_loop.run() (gateway 模式)                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 核心組件詳解

### 3.1 AgentLoop (`nanobot/agent/loop.py`)

**職責**: 核心處理引擎，協調所有 AI 代理操作

```python
class AgentLoop:
    def __init__(
        self,
        bus: MessageBus,           # 消息總線
        provider: LLMProvider,     # LLM 提供者
        workspace: Path,           # 工作目錄
        model: str,                # 模型名稱
        max_iterations: int,       # 最大工具迭代次數
        context_window_tokens: int, # 上下文窗口大小
        web_config: WebToolsConfig, # Web 工具配置
        exec_config: ExecToolConfig, # 執行工具配置
        cron_service: CronService, # 定時任務服務
        session_manager: SessionManager, # 會話管理
        mcp_servers: dict,         # MCP 服務器配置
        unified_session: bool,     # 統一會話模式
    ):
```

**初始化流程**:
1. 註冊默認工具 (`_register_default_tools()`)
   - Filesystem: ReadFile, WriteFile, EditFile, ListDir
   - Search: Glob, Grep
   - Web: WebSearch, WebFetch
   - Exec: Shell 命令執行
   - Message: 發送消息到通道
   - Spawn: 創建子代理
   - Cron: 定時任務管理

2. 初始化子代理管理器 (`SubagentManager`)
3. 初始化會話壓縮器 (`Consolidator`)
4. 初始化記憶鞏固 (`Dream`)

### 3.2 MessageBus (`nanobot/bus/queue.py`)

**職責**: 內部消息隊列，解耦輸入通道和代理處理

```python
class MessageBus:
    async def publish_inbound(self, msg: InboundMessage)
    async def consume_inbound(self) -> InboundMessage
    async def publish_outbound(self, msg: OutboundMessage)
```

### 3.3 SessionManager (`nanobot/session/manager.py`)

**職責**: 管理會話歷史，持久化到 JSONL 文件

```python
class SessionManager:
    def get_or_create(self, key: str) -> Session
    def save(self, session: Session)
    def _load(self, key: str) -> Session | None
```

**存儲結構**:
```
workspace/
└── sessions/
    ├── api_default.jsonl
    ├── telegram_user123.jsonl
    └── slack_C12345.jsonl
```

### 3.4 CronService (`nanobot/cron/service.py`)

**職責**: 管理定時任務（僅 gateway 模式）

```python
class CronService:
    def add_job(self, job: CronJob)
    def start(self)
    async def run_job(self, job: CronJob)
```

**內置任務**:
- `dream`: 記憶鞏固（每 2 小時）
- 用戶自定義任務

---

## 4. 數據流

### 4.1 請求處理流程 (API 模式)

```
HTTP Request (/v1/chat/completions)
         │
         ▼
┌─────────────────────────┐
│ handle_chat_completions │  (nanobot/api/server.py:64)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ agent_loop.process_direct │
│ - 獲取會話鎖             │
│ - 調用 _process_message  │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ _process_message        │  (nanobot/agent/loop.py:481)
│ - 獲取/創建會話          │
│ - 運行 consolidator      │
│ - 調用 _run_agent_loop   │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ _run_agent_loop         │  (nanobot/agent/loop.py:300)
│ - 創建 Hook              │
│ - 調用 AgentRunner.run   │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ AgentRunner.run         │  (nanobot/agent/runner.py)
│ - LLM 調用               │
│ - 工具執行               │
│ - 迭代循環               │
└───────────┬─────────────┘
            │
            ▼
HTTP Response (JSON)
```

### 4.2 消息處理流程 (Gateway 模式)

```
外部通道 (Telegram/Slack/etc.)
         │
         ▼
┌─────────────────────────┐
│ Channel.receive()       │
│ - 解析消息              │
│ - 發布到 MessageBus     │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ AgentLoop.run()         │
│ - 消費 InboundMessage   │
│ - 創建 asyncio.Task     │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ _dispatch()             │
│ - 會話鎖                │
│ - 並發控制              │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ _process_message()      │
│ - 構建上下文            │
│ - 運行 agent loop       │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Channel.send()          │
│ - 發送響應到通道        │
└─────────────────────────┘
```

---

## 5. Vanna AI 集成

### 5.1 VannaSQL 工具 (`nanobot/agent/tools/vanna_tool.py`)

**職責**: Text-to-SQL 生成與執行

```python
class VannaSQL:
    def __init__(self, database_url, model_name, api_key)
    def train_schema(self, force=False) -> Dict
    def generate_sql(self, question: str) -> str
    def execute(self, sql: str) -> List[Dict]
```

**初始化流程**:
```python
# 使用 ChromaDB 持久化
persist_dir = os.getenv("VANNA_PERSIST_DIR", "/app/data/vanna_db")
chroma_client = chromadb.PersistentClient(path=persist_dir)
self._vn = ChromaDB_VectorStore(chroma_client=chroma_client)

# 連接 PostgreSQL
self._vn.connect_to_postgres(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=os.getenv("POSTGRES_PORT", "5432"),
    dbname=os.getenv("POSTGRES_DB", "annual_reports"),
    user=os.getenv("POSTGRES_USER", "postgres"),
    password=os.getenv("POSTGRES_PASSWORD", "...")
)
```

### 5.2 訓練數據 (`vanna-service/data/`)

```
vanna-service/
└── data/
    ├── ddl.json            # 數據庫 Schema (11 張表)
    ├── ddl_whitelist.json  # DDL 白名單驗證
    ├── documentation.json  # Schema 文檔
    └── sql_pairs.json      # 問題-SQL 配對 (100+ 示例)
```

**訓練流程**:
```python
def train_schema(self):
    # 1. 訓練 DDL
    for ddl in self._get_table_ddl():
        self.vn.train(ddl=ddl)
    
    # 2. 訓練文檔
    for doc in self._get_schema_docs():
        self.vn.train(documentation=doc)
    
    # 3. 訓練示例查詢
    for sql, question in self._get_example_queries():
        self.vn.train(question=question, sql=sql)
```

### 5.3 數據庫 Schema

**核心表**:
1. `companies`: 公司主數據
2. `financial_metrics`: 財務指標
3. `market_data`: 市場數據
4. `key_personnel`: 關鍵人員
5. `shareholdings`: 持股信息
6. `revenue_breakdown`: 收入明細
7. `debt_maturity`: 債務到期
8. `specific_events`: 特定事件
9. `document_pages`: 文檔頁面 (Markdown)
10. `listing_applications`: 上市申請

**視圖**:
- `v_companies_resolved`: 自動選擇最佳公司名稱

---

## 6. 數據 ingestion 流程

### 6.1 DocumentPipeline (`nanobot/ingestion/pipeline.py`)

**職責**: PDF 文檔處理管道

```
PDF 文件
   │
   ▼
┌─────────────────────────┐
│ 1. Parser (VisionParser) │
│    - PDF → Markdown      │
│    - 提取表格/圖片       │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 2. PageClassifier        │
│    - LLM 語義分類        │
│    - 找出目標頁面        │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 3. FinancialAgent        │
│    - LLM 提取結構化數據  │
│    - 輸出 JSON           │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 4. Validator             │
│    - 數學規則驗證        │
│    - 數據完整性檢查      │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 5. DBClient              │
│    - 數據入庫            │
│    - 漸進式更新          │
└─────────────────────────┘
```

### 6.2 漸進式數據充實架構

**公司信息更新策略** (`nanobot/ingestion/repository/db_client.py:74-198`):

```python
async def upsert_company(self, stock_code, name_en, name_zh, ...):
    # 1. 查找現有公司
    existing = await self.get_company_by_stock_code(normalized_code)
    
    if existing:
        # 2. 按需更新（只填空值，不覆蓋已有數據）
        update_fields = {}
        
        # 名字來源區分
        if name_source == "index":  # 恆指報表（權威）
            update_fields['name_en_index'] = name_en
        else:  # PDF 擷取
            if not existing.get('name_en_extracted'):
                update_fields['name_en_extracted'] = name_en
        
        # 其他欄位只更新空值
        if industry and not existing.get('industry'):
            update_fields['industry'] = industry
        
        # 執行更新
        await self.update_company(company_id, update_fields)
    else:
        # 3. 創建新公司
        await self.insert_company(insert_data)
```

---

## 7. 配置管理

### 7.1 Config Schema (`nanobot/config/schema.py`)

```python
class Config(BaseSettings):
    agents: AgentsConfig
    providers: ProvidersConfig
    tools: ToolsConfig
    channels: ChannelsConfig
    api: APIConfig
    gateway: GatewayConfig
    workspace_path: Path
```

### 7.2 環境變數解析

```python
# config.json
{
    "providers": {
        "openai": {
            "api_key": "${OPENAI_API_KEY}"
        }
    }
}

# 啟動時自動解析
config = resolve_config_env_vars(load_config())
```

---

## 8. 代碼問題分析

### 8.1 Vanna 相關問題 ⚠️

#### 問題 1: 硬編碼的數據庫連接
**文件**: `nanobot/agent/tools/vanna_tool.py:49`
```python
self.database_url = database_url or "postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports"
```
**風險**: 
- 默認密碼未修改
- 端口 5433 與 ingestion 模塊的 5432 不一致

**建議修復**:
```python
self.database_url = database_url or os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:5432/annual_reports"
)
```

#### 問題 2: 缺少錯誤處理
**文件**: `nanobot/agent/tools/vanna_tool.py:93-95`
```python
except Exception as e:
    logger.error(f"Failed to create Vanna instance: {e}")
    raise  # 直接拋出，沒有 fallback
```
**建議**: 添加 fallback 機制，允許在 Vanna 不可用時降級為普通 SQL 執行

#### 問題 3: 訓練狀態未持久化
**文件**: `nanobot/agent/tools/vanna_tool.py:54`
```python
self._trained = False  # 內存狀態，重啟後丟失
```
**建議**: 將訓練狀態持久化到文件，避免每次重啟都重新訓練

### 8.2 Data/DB 相關問題 ⚠️

#### 問題 4: 數據庫連接管理
**文件**: `nanobot/ingestion/repository/db_client.py:35-46`
```python
async def connect(self):
    self.conn = await asyncpg.connect(self.db_url)

async def close(self):
    if self.conn:
        await self.conn.close()
```
**風險**: 
- 沒有連接池
- 沒有重連機制
- 沒有超時配置

**建議**: 使用 `asyncpg.create_pool()` 代替單連接

#### 問題 5: SQL 注入風險
**文件**: `nanobot/ingestion/repository/db_client.py`
```python
# ✅ 正確：使用參數化查詢
await self.conn.fetchrow(
    "SELECT * FROM companies WHERE stock_code = $1",
    normalized_code
)
```
**註**: 當前代碼已正確使用參數化查詢，但需要確保所有新代碼遵循此模式

#### 問題 6: 事務管理缺失
**文件**: `nanobot/ingestion/pipeline.py`
```python
# 多個數據庫操作沒有事務包裝
await db.upsert_company(...)
await db.insert_metrics(...)
await db.insert_revenue_breakdown(...)
```
**風險**: 如果中間失敗，會導致數據不一致

**建議**: 使用事務包裝相關操作
```python
async with db.conn.transaction():
    await db.upsert_company(...)
    await db.insert_metrics(...)
```

### 8.3 AgentLoop 相關問題 ⚠️

#### 問題 7: MCP 連接競爭條件
**文件**: `nanobot/agent/loop.py:256-276`
```python
async def _connect_mcp(self) -> None:
    if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
        return
    self._mcp_connecting = True
    try:
        # ... 連接邏輯
    finally:
        self._mcp_connecting = False
```
**風險**: 如果連接失敗，`_mcp_connecting` 會被設置為 False，但下次請求會重試。這可能導致頻繁的連接嘗試。

**建議**: 添加退避機制和錯誤計數

#### 問題 8: 會話鎖未清理
**文件**: `nanobot/agent/loop.py:204`
```python
self._session_locks: dict[str, asyncio.Lock] = {}
```
**風險**: 鎖對象會隨時間累積，沒有清理機制

**建議**: 添加定期清理或在使用後刪除空閒鎖

### 8.4 配置相關問題 ⚠️

#### 問題 9: 默認工作空間權限
**文件**: `nanobot/config/schema.py:65`
```python
workspace: str = "~/.nanobot/workspace"
```
**風險**: 默認工作空間在全局目錄，多用戶環境可能有權限問題

**建議**: 文檔中明確說明權限要求

---

## 9. 最佳實踐建議

### 9.1 數據庫
1. ✅ 使用參數化查詢防止 SQL 注入
2. ❌ 添加連接池
3. ❌ 添加事務管理
4. ❌ 添加重連機制

### 9.2 Vanna
1. ❌ 持久化訓練狀態
2. ❌ 添加 fallback 機制
3. ❌ 統一數據庫配置

### 9.3 AgentLoop
1. ❌ 添加 MCP 連接退避
2. ❌ 清理空閒會話鎖
3. ✅ 並發控制（已實現）

### 9.4 配置
1. ❌ 使用環境變數管理敏感信息
2. ❌ 添加配置驗證
3. ✅ 支持 camelCase 和 snake_case（已實現）

---

## 10. 參考文件

| 組件 | 文件路徑 | 說明 |
|------|----------|------|
| CLI 入口 | `nanobot/cli/commands.py` | 命令行接口 |
| API Server | `nanobot/api/server.py` | OpenAI 兼容 API |
| AgentLoop | `nanobot/agent/loop.py` | 核心處理引擎 |
| Vanna Tool | `nanobot/agent/tools/vanna_tool.py` | Text-to-SQL |
| DB Client | `nanobot/ingestion/repository/db_client.py` | 數據庫操作 |
| Pipeline | `nanobot/ingestion/pipeline.py` | PDF 處理管道 |
| Config | `nanobot/config/schema.py` | 配置 Schema |
| Session | `nanobot/session/manager.py` | 會話管理 |

---

## 11. 啟動命令示例

### API Server
```bash
nanobot serve --port 8000 --config ~/.nanobot/config.json
```

### Gateway Server
```bash
nanobot gateway --port 8080 --config ~/.nanobot/config.json
```

### 測試 API
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nanobot",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```
