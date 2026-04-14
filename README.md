<div align="center">
  <img src="nanobot_logo.png" alt="nanobot" width="500">
  <h1>nanobot: Financial Report Analysis Agent</h1>
  <p>
    <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/Docker-GPU+CUDA-5865F2" alt="Docker GPU">
  </p>
</div>

**nanobot** 是一个专注于金融年报/财务报告 PDF 解析与结构化数据提取的 AI Agent 系统。

基于 [nanobot-ai](https://github.com/HKUDS/nanobot) 核心框架，结合 OpenDataLoader Hybrid (Docling GPU) 和 Vanna AI (Text-to-SQL)，实现从 PDF 到结构化数据库的完整自动化流程。

---

## 📁 项目结构

```
nanobot/
├── nanobot/                     # 🧠 核心 Python 模块
│   ├── agent/                   #    Agent 逻辑层
│   │   ├── loop.py              #    主循环 (LLM ↔ Tool 执行)
│   │   ├── context.py           #    Prompt 构建
│   │   ├── memory.py            #    持久化记忆
│   │   └── tools/               #    🛠️ Agent Tools (Python 实现)
│   │       ├── pdf_parser.py    #       PDF 解析工具入口
│   │       ├── financial.py     #       财务数据查询工具
│   │       ├── vanna_tool.py    #       Text-to-SQL 工具
│   │       ├── db_ingestion_tools.py  #  数据入库工具
│   │       └── multimodal_rag.py      #  图文关联 RAG
│   │
│   ├── core/                    #    📄 PDF 核心处理层
│   │   └ pdf_core.py            #    OpenDataLoader 统一封装
│   │
│   ├── ingestion/               #    🔄 数据摄入 Pipeline (Python)
│   │   ├── pipeline.py          #    主 Pipeline 协调器
│   │   ├── agentic_pipeline.py  #    Agent-driven Pipeline
│   │   ├── stages/              #    ⚡ 5-Stage 处理流程
│   │   │   ├── stage0_preprocessor.py   #  PDF 预处理 (分批/页码)
│   │   │   ├── stage1_parser.py         #  Hybrid 解析 (Docling GPU)
│   │   │   ├── stage2_enrichment.py     #  图文关联/元数据增强
│   │   │   ├── stage3_router.py         #  关键字路由 (定位目标页)
│   │   │      └── stage4_extractor.py   #  LLM 结构化提取
│   │   ├── extractors/          #    提取器 (Revenue, Personnel...)
│   │   ├── parsers/             #    Parser 实现
│   │   └ utils/                 #    工具函数 (表格合并等)
│   │   └ repository/            #    数据库 Repository
│   │   └ validators/            #    数据校验器
│   │
│   ├── skills/                  #    🎯 Skills (Agent 行为定义)
│   │   ├── financial-analysis/  #       财务分析 Skill
│   │   ├── ingestion/           #       摄入 Skill
│   │   └ memory/                #       记忆管理 Skill
│   │   └ github/                #       GitHub Skill
│   │   └ weather/               #       天气 Skill
│   │   └── ...                  #       其他 Skills
│   │
│   ├── providers/               #    🤖 LLM Providers
│   ├── channels/                #    📱 Chat Channel 集成
│   ├── cron/                    #    ⏰ 定时任务
│   ├── heartbeat/               #    💓 周期唤醒
│   ├── session/                 #    💬 会话管理
│   └ config/                    #    ⚙️ 配置 Schema
│   └ cli/                       #    🖥️ CLI 命令
│   └ utils/                     #    工具函数
│   └ templates/                 #    Jinja2 模板
│
├── webui/                       # 🌐 Web UI (FastAPI + React)
│   ├── app/
│   │   ├── api/                 #    REST API 端点
│   │   ├── core/                #    核心配置
│   │   ├── services/            #    业务服务
│   │   └ schemas/               #    Pydantic Schema
│   ├── static/                  #    前端静态文件
│   ├── Dockerfile.gpu           #    GPU 版 Dockerfile
│   └ entrypoint_delayed.sh      #    启动脚本 (等待 Hybrid)
│
├── vanna-service/               # 🧠 Vanna AI (Text-to-SQL)
│   ├── start.py                 #    启动入口
│   ├── vanna_training.py        #    训练脚本
│   ├── ddl.json                 #    DDL 知识库
│   ├── sql_pairs.json           #    SQL 示例知识库
│   ├── documentation.json       #    文档知识库
│   └ Dockerfile
│
├── bridge/                      # 🔗 WhatsApp 等桥接
├── config/                      # ⚙️ 运行时配置
├── data/                        # 📂 数据目录
│   ├── raw/                     #    原始 PDF / 搜索关键词
│   ├── uploads/                 #    上传文件
│   ├── output/                  #    输出结果
│   ├── vanna/                   #    ChromaDB 存储
│
├── storage/                     # 💾 数据库初始化 SQL
├── scripts/                     # 🛠️ 辅助脚本
├── tests/                       # 🧪 测试
├── docs/                        # 📚 文档
│
├── docker-compose.gpu.yml       # 🐳 GPU 版 Compose
├── Dockerfile                   # 🐳 CPU 版 Dockerfile
└── Dockerfile.gpu               # 🐳 GPU 版 Dockerfile
```

---

## 🔄 完整工作流程

### PDF 处理 Pipeline (5-Stage)

```
PDF 上传
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 0: Preprocessor (Python)                             │
│  ├─ PDF 预处理                                               │
│  ├─ 大文件分批 (>100页 → 每批10页)                           │
│  ├─ 页码范围检测                                             │
│  └─ 输入验证                                                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: Parser (Python + OpenDataLoader Hybrid)           │
│  ├─ 调用 OpenDataLoader Core                                │
│  ├─ Hybrid 模式: Docling GPU (CUDA)                         │
│  ├─ 输出: Markdown + JSON Artifacts                          │
│  ├─ 提取: Tables, Images, Text Chunks                       │
│  └─ 跨页表格合并                                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 2: Enrichment (Python)                               │
│  ├─ 图文关联映射                                             │
│  ├─ 元数据增强                                               │
│  ├─ OCR 文字补充                                             │
│  └─ 保存所有页面到兜底表 (Zone 2)                            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 3: Router (Python + LLM)                             │
│  ├─ 关键字扫描                                               │
│  ├─ 定位目标页面                                             │
│  ├─ 使用 search_keywords.json                                │
│  └─ 输出: 候选页面列表                                       │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 4: Extractor (Python + LLM)                          │
│  ├─ LLM 结构化提取                                           │
│  ├─ Revenue Breakdown (收入分解)                             │
│  ├─ Key Personnel (关键人员)                                 │
│  ├─ Financial Metrics (财务指标)                             │
│  ├─ 写入 structured_extraction 表 (Zone 1)                   │
│  └─ 保存 output.json                                         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 8-10: Post-Processing                                  │
│  ├─ 图文关联映射 (跨模态 Magic)                              │
│  ├─ 触发 Vanna 训练                                          │
│  └─ 更新文档状态                                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
数据库 (PostgreSQL + pgvector)
```

---

## 🛠️ 处理层次: Agent Tool vs Python

| 处理层 | 实现方式 | 说明 |
|--------|----------|------|
| **PDF 解析** | Python (`OpenDataLoaderCore`) | 调用 Docling GPU 模型，不经过 LLM |
| **表格提取** | Python (Hybrid Parser) | 端到端表格识别，不经过 LLM |
| **图片提取** | Python (Hybrid Parser) | 端到端图片识别 + OCR，不经过 LLM |
| **跨页表格合并** | Python (`table_merger`) | 算法合并，不经过 LLM |
| **关键字路由** | Python + LLM (`Stage3Router`) | LLM 判断页面相关性 |
| **结构化提取** | Python + LLM (`Stage4Extractor`) | LLM 从表格/文字提取结构化数据 |
| **SQL 生成** | Vanna AI (Python + LLM) | Text-to-SQL，LLM 生成 SQL |
| **数据入库** | Python (`Repository`) | SQLAlchemy 写入数据库 |
| **用户交互** | Agent Tool (`pdf_parser`) | LLM 调用 tool 触发 pipeline |
| **财务查询** | Agent Tool (`vanna_tool`) | LLM 调用 Vanna 生成 SQL |

### 详细说明

#### 🐍 Python 直接处理 (不经过 LLM)

这些任务由 Python 代码直接执行，无需 LLM 参与，**速度快、成本低**：

1. **PDF 解析 (Stage 1)**: OpenDataLoader Hybrid 模式调用 Docling 模型
2. **表格/图片识别**: Docling GPU 模型端到端识别
3. **跨页表格合并**: 算法检测相邻表格并合并
4. **图片 Base64 编码**: 自动转换临时目录图片为 Base64
5. **数据入库**: Repository 层直接写入 PostgreSQL
6. **Vanna 训练**: 自动学习 DDL 和 SQL 示例

#### 🧠 LLM 增强 (Python + LLM)

这些任务需要 LLM 的语义理解能力：

1. **关键字路由 (Stage 3)**: LLM 判断页面是否包含目标信息
2. **结构化提取 (Stage 4)**: LLM 从表格/文字中提取结构化字段
3. **SQL 生成 (Vanna)**: Text-to-SQL，根据自然语言生成 SQL
4. **财务分析问答**: Agent 对话式查询

#### 🛠️ Agent Tool 入口

Agent 通过 Tool 调用触发底层 Python 处理：

| Tool | 底层 Python | 功能 |
|------|-------------|------|
| `parse_pdf` | `pipeline.process_pdf_full()` | 触发完整 5-Stage 流程 |
| `query_financial` | `vanna.generate_sql()` | 财务数据查询 |
| `search_documents` | `multimodal_rag.search()` | 图文关联搜索 |
| `ingest_document` | `db_ingestion_tools` | 文档入库 |

---

## 🎯 Skills vs Tools

| 类型 | 位置 | 定义 | 作用 |
|------|------|------|------|
| **Tool** | `nanobot/agent/tools/*.py` | Python 函数 | 执行具体操作 |
| **Skill** | `nanobot/skills/*/SKILL.md` | Markdown 指令 | 定义 Agent 行为模式 |

**Skill 示例** (`financial-analysis/SKILL.md`):

```markdown
# Financial Analysis Skill

When user asks about financial reports:
1. Use `parse_pdf` tool to process uploaded PDF
2. Use `query_financial` tool to retrieve structured data
3. Present results in markdown tables
```

**Tool 示例** (`tools/pdf_parser.py`):

```python
@tool
async def parse_pdf(pdf_path: str) -> dict:
    """Parse PDF and extract structured data."""
    result = await pipeline.process_pdf_full(pdf_path)
    return result
```

---

## 🚀 快速启动

### Docker GPU 版 (推荐)

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 设置 DASHSCOPE_API_KEY

# 2. 启动所有服务
docker compose -f docker-compose.gpu.yml up -d

# 3. 查看状态
docker compose -f docker-compose.gpu.yml ps

# 4. 访问 Web UI
open http://localhost:3000
```

### 服务列表

| 服务 | 端口 | 说明 |
|------|------|------|
| `nanobot-webui` | 3000 | Web UI + Hybrid Server |
| `nanobot-gateway` | 8081, 18790 | Agent Gateway |
| `postgres-financial` | 5433 | PostgreSQL + pgvector |
| `vanna-service` | 8082 | Vanna AI (内部) |

---

## 🎯 年报 Agent Skills 详解

Agent 通过 **Skills** 定义行为模式，通过 **Tools** 执行具体操作。年报处理涉及以下核心 Skills：

### Skills 概览

```
┌─────────────────────────────────────────────────────────────┐
│  年报 Agent Skills 架构                                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📊 financial-analysis       财务分析核心 Skill             │
│     ├─ parse_financial_pdf     PDF 解析                     │
│     ├─ query_financial_database 数据库查询                  │
│     ├─ search_documents        文档语义搜索                  │
│     ├─ analyze_chart           图表分析                      │
│     └─ resolve_entity          公司名解析                    │
│                                                             │
│  📄 ingestion               文档摄入 Skill                   │
│     ├─ Rule A: 行业确认规则     (指数报告)                   │
│     ├─ Rule B: AI 行业提取规则  (年报)                       │
│     ├─ smart_insert_document   智能入库                      │
│     └─ update_document_status  状态更新                      │
│                                                             │
│  📑 document-indexer         导航地图 Skill                  │
│     ├─ 建立索引地图             TOC + Metadata               │
│     ├─ 精确页码定位             战略分析                      │
│     ├─ 多文件对比               YoY / 跨公司                  │
│     └─ Sub-agent 精准提取      Map & Strike 模式             │
│                                                             │
│  🧠 memory                  记忆管理 Skill                   │
│  📋 summarize               文档摘要 Skill                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 📊 Financial Analysis Skill

**用途**: 分析年报和财务文档，100% 数值准确。

#### 5 个核心 Tools

| Tool | 用途 | 输入 | 输出 |
|------|------|------|------|
| `parse_financial_pdf` | PDF 解析 | `pdf_path`, `extract_tables` | Markdown + Tables + Charts |
| `query_financial_database` | 数据库查询 | `query` (自然语言或 SQL) | 结构化数据 + Citations |
| `search_documents` | 文档搜索 | `query`, `company`, `year` | 文本 chunks + Sources |
| `analyze_chart` | 图表分析 | `page`, `chart_index` | 图表类型 + 数据点 |
| `resolve_entity` | 公司名解析 | `name` (任意变体) | 标准名 + Stock Code |

#### 意图路由 (选择正确工具)

```
用户问题
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  意图分析                                                    │
│                                                             │
│  需要精确数字？                                              │
│  ├─ Yes → query_financial_database (Text-to-SQL)            │
│  │         ├─ 营收、利润、增长率                            │
│  │         ├─ 排行榜、趋势分析                              │
│  │         └─ 跨年比较                                      │
│  │                                                          │
│  ├─ 需要解释/策略？                                          │
│  │  └ search_documents (语义检索)                           │
│  │     ├─ 业务描述、战略分析                                │
│  │     ├─ 风险因素、管理层讨论                              │
│  │     └─ 非结构化文本                                      │
│  │                                                          │
│  ├─ 需要精确页码/表格？                                      │
│  │  └ document-indexer (导航地图)                           │
│  │     ├─ 原始表格验证                                      │
│  │     ├─ 图表提取                                          │
│  │     └─ Citation 溯源                                     │
│  │                                                          │
│  └─ 提到图表？                                               │
│     └ analyze_chart (VLM 分析)                              │
│        ├─ 图表类型识别                                      │
│        ├─ 数据点提取                                        │
│        └─ 洞察解读                                          │
└─────────────────────────────────────────────────────────────┘
```

#### Tool 使用示例

**1. PDF 解析**:
```python
result = parse_financial_pdf("tencent_2023_ar.pdf", extract_tables=True)
# Returns:
# {
#   markdown: "...",
#   tables: [{headers, rows, page}],
#   charts: [{type, description, page}],
#   citations: [{source_file, page}]
# }
```

**2. 数据库查询** (自然语言 → SQL):
```python
# 自然语言查询
result = query_financial_database("Show Tencent's revenue for 2020-2023")

# 或直接 SQL
result = query_financial_database(
    sql="SELECT year, standardized_value FROM financial_metrics 
         WHERE company_id = 1 AND metric_name = 'Revenue'"
)
```

**3. 公司名解析**:
```python
resolve_entity("腾讯")
# Returns: {en: "Tencent Holdings", zh: "腾讯控股", code: "00700"}

resolve_entity("阿里巴巴")
# Returns: {en: "Alibaba Group", zh: "阿里巴巴集团", code: "09988"}
```

---

### 📄 Ingestion Skill

**用途**: 智能文档摄入，自动判断行业规则。

#### 行业双轨制规则

```
┌─────────────────────────────────────────────────────────────┐
│  Rule A: 指数报告 - 行业确认                                  │
│                                                             │
│  触发条件:                                                   │
│  ├─ 报告标题包含 "Index", "恒生指数", "HSI"                  │
│  ├─ 报告明确定义单一行业主题                                  │
│  │                                                          │
│  行为:                                                       │
│  ├─ confirmed_industry = "Biotech" (从标题提取)             │
│  ├─ is_industry_confirmed = TRUE                            │
│  ├─ 所有成分股 → 强制同一行业                                 │
│  └─ industry_source = "confirmed"                           │
│                                                             │
│  示例:                                                       │
│  "恒生生物科技指数 Q3 2024"                                  │
│  → 所有公司: confirmed_industry = "Biotech"                  │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Rule B: 年报 - AI 行业提取                                   │
│                                                             │
│  触发条件:                                                   │
│  ├─ 年度报告 (Annual Report)                                 │
│  ├─ 无单一行业主题                                           │
│  │                                                          │
│  行为:                                                       │
│  ├─ confirmed_industry = NULL                               │
│  ├─ is_industry_confirmed = FALSE                           │
│  ├─ AI 提取多个可能行业                                       │
│  ├─ 存入 ai_extracted_industries (JSONB Array)              │
│  └─ industry_source = "ai_predict"                          │
│                                                             │
│  示例:                                                       │
│  "腾讯控股 2023 年报"                                        │
│  → ai_extracted_industries = ["Technology", "Gaming", ...]   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Ingestion Tools

| Tool | 用途 | 输入 |
|------|------|------|
| `smart_insert_document` | 智能入库 | `filename`, `report_type`, `confirmed_doc_industry`, `sub_companies` |
| `get_db_schema` | 查看 Schema | - |
| `update_document_status` | 更新状态 | `document_id`, `status` |

#### 数据库写入示例

```json
// Rule A: 指数报告
{
  "filename": "hsi_biotech_q3_2024.pdf",
  "report_type": "index_report",
  "confirmed_doc_industry": "Biotech",
  "industry_assignment_rule": "A",
  "sub_companies": [
    {"name": "Sino Biopharmaceutical", "stock_code": "01177"},
    {"name": "Wuxi Biologics", "stock_code": "02269"}
  ]
}

// Rule B: 年报
{
  "filename": "tencent_2023_ar.pdf",
  "report_type": "annual_report",
  "parent_company": "Tencent Holdings",
  "industry_assignment_rule": "B",
  "sub_companies": [
    {
      "name": "Tencent Music",
      "ai_industries": ["Technology", "Entertainment"]
    }
  ]
}
```

---

### 📑 Document Indexer Skill

**用途**: 长篇年报的「导航地图」系统，Map & Strike 模式。

#### 工作流程

```
用户请求: [Doc: /path/to/report.pdf] "找出营收数据"
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: 建立地图 (Map Discovery)                          │
│                                                             │
│  ├─ 检查索引是否存在                                         │
│  │  workspace/indexes/<doc_name>/                           │
│  │                                                          │
│  ├─ 若不存在，执行:                                          │
│  │  build_indexes.py "<pdf_path>"                           │
│  │                                                          │
│  ├─ 生成:                                                    │
│  │  ├─ metadata.md      (公司名、年份、Stock Code)           │
│  │  ├─ toc.md           (目录结构)                           │
│  │  └─ navigation_context.md (前 5 页摘要)                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: 战略分析 (Strategic Planning)                     │
│                                                             │
│  ├─ 读取 metadata.md                                        │
│  │  → 确认公司: "Tencent Holdings"                          │
│  │  → 确认年份: 2023                                         │
│  │                                                          │
│  ├─ 读取 toc.md                                             │
│  │  → 搜索 "Revenue", "收入", "财务报表"                     │
│  │  → 定位: "财务报表" → Physical Page: 45                   │
│  │                                                          │
│  ├─ 输出:                                                    │
│  │  "营收数据极可能在第 45 页"                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: Sub-agent 精准提取 (Strike)                       │
│                                                             │
│  ├─ 主 Agent 指派 Sub-agent                                  │
│  │                                                          │
│  ├─ Sub-agent 执行:                                          │
│  │  "读取第 45 页，提取营收表格"                             │
│  │                                                          │
│  ├─ 使用 PyMuPDF 直接读取                                     │
│  │                                                          │
│  ├─ 返回:                                                    │
│  │  Markdown 表格 + Citation                                │
│  │  "(Data from Physical Page: 45)"                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 生成的索引文件

```
workspace/indexes/tencent_2023_ar/
├── metadata.md              # 公司全称、Stock Code、年份
│   ---
│   Company: Tencent Holdings Limited
│   Stock Code: 00700.HK
│   Year: 2023
│   ---
│
├── toc.md                   # 目录结构 + 物理页码
│   1. 主席报告 ─────────── Physical Page: 12
│   2. 业务回顾 ─────────── Physical Page: 20
│   3. 财务报表 ─────────── Physical Page: 45
│   4. ESG 报告 ──────────── Physical Page: 80
│
└── navigation_context.md    # 前 5 页摘要
    结构概述、关键章节位置
```

---

### 🛠️ Agent Tools vs Pipeline 关系

| 层级 | Tool | 调用 Pipeline | 说明 |
|------|------|---------------|------|
| **用户交互** | `parse_financial_pdf` | `pipeline.process_pdf_full()` | 触发完整 5-Stage |
| **数据查询** | `query_financial_database` | `vanna_tool.generate_sql()` | Text-to-SQL |
| **语义搜索** | `search_documents` | `multimodal_rag.search()` | 图文关联 |
| **入库操作** | `smart_insert_document` | `db_ingestion_tools` | Schema v2.3 写入 |
| **实体解析** | `resolve_entity` | `entity_resolver` | CN/EN 名称映射 |

#### Tool → Pipeline 调用链

```
Agent Tool
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  parse_financial_pdf(pdf_path)                              │
│                                                             │
│  → 调用: pipeline.process_pdf_full(pdf_path)                │
│                                                             │
│  → 执行:                                                     │
│     Stage 0: Preprocessor                                   │
│     Stage 1: Parser (Hybrid)                                │
│     Stage 2: Enrichment                                     │
│     Stage 3: Router                                         │
│     Stage 4: Extractor                                      │
│     Step 8-10: Post-Processing                              │
│                                                             │
│  → 返回:                                                     │
│     {markdown, tables, charts, structured_data, doc_id}     │
└─────────────────────────────────────────────────────────────┘
```

---

### 🎯 年报处理完整流程

```
用户上传年报 PDF
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Agent 接收请求                                           │
│     ├─ 识别意图: "解析年报"                                   │
│     ├─ 选择 Skill: financial-analysis                        │
│     └─ 选择 Tool: parse_financial_pdf                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Pipeline 5-Stage 处理                                    │
│     ├─ Stage 0: 验证 + 分批                                  │
│     ├─ Stage 1: Docling GPU 解析                             │
│     ├─ Stage 2: 图文关联 + 兜底写入                          │
│     ├─ Stage 3: 关键字路由                                   │
│     └─ Stage 4: LLM 结构化提取                               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  3. 数据入库                                                 │
│     ├─ Zone 1: financial_metrics (EAV)                      │
│     ├─ Zone 2: document_pages (兜底)                         │
│     ├─ JSONB: companies.extra_data                          │
│     └─ Vanna Training 自动触发                               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  4. 用户查询                                                 │
│     ├─ Agent 选择 Tool: query_financial_database             │
│     ├─ Vanna 生成 SQL                                        │
│     ├─ 执行查询                                               │
│     └─ 返回结果 + Citation                                   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
返回给用户: 数值表格 + 溯源信息
```

---

## 🤖 Agent Query 功能详解

Agent 通过 `vanna_tool.py` 实现自然语言到 SQL 的转换，支持以下功能：

### 1. Text-to-SQL 查询 (核心功能)

```python
# 用户问问题
question = "CK Hutchison 2023 年收入是多少？"

# Vanna 自动生成 SQL
sql = vanna.generate_sql(question)
# → SELECT standardized_value FROM financial_metrics 
#    WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') 
#    AND metric_name = 'Revenue' AND year = 2023

# 执行查询
results = vanna.execute(sql)
```

### 2. Dynamic Schema Injection (智能 JSONB 查询)

**特色功能**：自动发现 JSONB 动态属性并注入提示

```python
# 自动发现 companies.extra_data 中的 Keys
dynamic_info = await vanna.discover_dynamic_keys()
# → {"discovered_keys": ["index_quarter", "index_theme", "is_audited", ...]}

# 构建增强提示
enhanced_prompt = vanna.build_enhanced_prompt(question, dynamic_info)

# 生成正确的 JSONB 查询语法
sql = await vanna.generate_sql_with_dynamic_schema("找 Q3 指数报告")
# → SELECT * FROM documents WHERE dynamic_attributes->>'index_quarter' = 'Q3'
```

### 3. 支持的查询类型

| 查询类型 | 示例问题 | 查询表 |
|----------|----------|--------|
| **公司信息** | "列出所有生物科技公司" | `companies`, `v_companies_for_vanna` |
| **财务指标** | "腾讯 2023 年收入" | `financial_metrics` |
| **关键人员** | "审计委员会成员" | `key_personnel` (JSONB `committee_membership`) |
| **股东结构** | "控股股东是谁" | `shareholding_structure` |
| **收入分解** | "按地区收入分布" | `revenue_breakdown` |
| **市场数据** | "股价走势" | `market_data` |
| **文档搜索** | "ESG 相关内容" | `document_pages` (Fallback) |

### 4. 完整 Query 流程

```
用户问题: "CK Hutchison 2023 年收入是多少？"
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Dynamic Key Discovery                                   │
│     ├─ 扫描 companies.extra_data 发现动态 Keys              │
│     ├─ 扫描 document_companies.extracted_industries         │
│     └─ 返回: {"index_quarter", "index_theme", ...}          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Enhanced Prompt Build                                   │
│     ├─ 注入 JSONB 查询语法提示                               │
│     ├─ 注入 v2.3 Schema 变更提醒                            │
│     └─ 添加 SQL 范例参考                                     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  3. RAG Retrieval (ChromaDB)                                │
│     ├─ 搜索相似 DDL (表结构)                                 │
│     ├─ 搜索相似 SQL 范例                                     │
│     └─ 搜索 Documentation (语义说明)                        │
│     → 返回 Top-K 相关上下文                                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  4. LLM SQL Generation                                      │
│     ├─ 接收: 问题 + RAG 上下文 + JSONB 提示                  │
│     ├─ 生成: PostgreSQL 兼容 SQL                            │
│     └─ 确保: v2.3 Schema 适配                               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  5. SQL Execution                                           │
│     ├─ 执行 SQL 查询                                         │
│     ├─ 返回结果 DataFrame                                    │
│     └─ 可选: LLM 总结结果                                    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
返回给用户: [{"year": 2023, "standardized_value": 3456.78}]
```

---

## 🧠 Vanna Training 详解

Vanna 通过三层数据学习如何生成正确的 SQL：

### 训练三要素

```
┌─────────────────────────────────────────────────────────────┐
│  1. DDL (表结构定义)                                         │
│     ├─ CREATE TABLE 语句                                     │
│     ├─ 字段名称、类型、约束                                   │
│     ├─ JSONB 字段说明                                        │
│     └─ 17 张表 + 3 个视图                                    │
│                                                             │
│  2. Documentation (语义说明)                                 │
│     ├─ 表用途说明                                             │
│     ├─ 字段含义解释                                          │
│     ├─ 查询最佳实践                                          │
│     └─ ⚠️ v2.3 字段变更提醒                                  │
│                                                             │
│  3. SQL Examples (问答范例)                                  │
│     ├─ question: 自然语言问题                                │
│     ├─ sql: 正确的 SQL                                       │
│     └─ 20+ 常用查询场景                                      │
└─────────────────────────────────────────────────────────────┘
```

### 训练时机

| 场景 | 触发 | 说明 |
|------|------|------|
| **启动时** | `vanna-service` 启动 | 自动训练 Schema + Enhanced Data |
| **新文档入库后** | `pipeline.process_pdf_full()` Step 9 | 调用 `/api/train?doc_id=xxx` |
| **手动触发** | API `/api/train` | 后台异步训练 |

### 训练数据来源

```
vanna-service/
├── vanna_training.py           # 训练数据生成器
│   ├── _get_enhanced_ddl()             # 17 张表 DDL
│   ├── _get_enhanced_documentation()   # 每张表语义说明
│   └── _get_enhanced_sql_examples()    # 20+ 问答范例
│
├── ddl.json                    # DDL JSON 文件
├── documentation.json          # Documentation JSON 文件
├── sql_pairs.json              # SQL 范例 JSON 文件
│
└── data/chromadb/              # ChromaDB 持久化存储
    ├── 训练向量 embeddings
    └── 问题 → SQL 映射
```

### 训练示例代码

```python
# DDL 训练
vn.train(ddl="CREATE TABLE companies (stock_code VARCHAR(50), name_en VARCHAR(255), ...)")

# Documentation 训练
vn.train(documentation="companies 表存上市公司信息。stock_code 格式如 00001 (港股)。双轨制行业系统：is_industry_confirmed=TRUE 时使用 confirmed_industry")

# SQL 范例训练
vn.train(
    question="CK Hutchison 2023 年收入是多少？",
    sql="SELECT standardized_value FROM financial_metrics WHERE company_id = (SELECT id FROM companies WHERE stock_code = '00001') AND metric_name = 'Revenue' AND year = 2023"
)

# 针对特定文档训练
train_vanna_on_document(doc_id="stock_00001_2023")
```

### v2.3 Schema 变更处理

训练时自动注入字段变更提醒，确保生成的 SQL 使用正确字段名：

```sql
-- ❌ 旧版 (v2.2) 错误查询
SELECT * FROM document_pages WHERE company_id = 1

-- ✅ 新版 (v2.3) 正确查询
SELECT dp.* FROM document_pages dp
JOIN documents d ON dp.document_id = d.id
WHERE d.owner_company_id = 1
```

**字段变更映射**：

| 表 | 旧字段 | 新字段 |
|----|--------|--------|
| `market_data` | `trade_date` | `data_date` |
| `market_data` | `closing_price` | `close_price` |
| `market_data` | `trading_volume` | `volume` |
| `revenue_breakdown` | `category` | `segment_name` |
| `revenue_breakdown` | `amount` | `revenue_amount` |
| `key_personnel` | `person_name` | `name_en` |
| `key_personnel` | `committee` | `committee_membership` (JSONB) |
| `document_pages` | `company_id` | **已删除** (需 JOIN documents) |

---

## 🔌 Vanna API Endpoints

| Endpoint | 功能 | 参数 |
|----------|------|------|
| `POST /api/ask` | 自然语言查询 | `question`, `include_sql`, `include_summary` |
| `POST /api/train` | 触发训练 | `train_type` (schema/ddl/sql), `doc_id` |
| `POST /api/train_ddl` | 训练 DDL | `ddl` 字符串 |
| `POST /api/train_sql` | 训练 SQL 范例 | `question`, `sql` |
| `POST /api/extract` | LLM 信息提取 | `text`, `extract_type` |
| `GET /api/column_changes` | v2.3 字段变更说明 | — |
| `GET /health` | 健康检查 | — |
| `GET /status` | 服务状态 | — |

### API 使用示例

```bash
# 自然语言查询
curl -X POST http://localhost:8082/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "CK Hutchison 2023 年收入", "include_sql": true}'

# 返回结果
{
  "question": "CK Hutchison 2023 年收入",
  "sql": "SELECT standardized_value FROM financial_metrics WHERE...",
  "data": [{"standardized_value": 3456.78}],
  "status": "ready"
}

# 触发训练
curl -X POST http://localhost:8082/api/train \
  -H "Content-Type: application/json" \
  -d '{"train_type": "schema"}'

# 查看字段变更
curl http://localhost:8082/api/column_changes
```

---

## 📊 数据库 Schema

### Zone 1: 结构化数据表

```sql
-- 结构化提取结果
structured_extraction (
    id, document_id, company_id, year,
    extraction_type,  -- revenue_breakdown, key_personnel, financial_metrics
    extracted_data,   -- JSON 结构化数据
    source_pages,     -- 来源页码
    confidence_score
)

-- 财务指标表
financial_metrics (
    id, company_id, year,
    revenue, net_income, total_assets,
    roe, roa, debt_ratio, ...
)
```

### Zone 2: 兜底表 (所有页面)

```sql
-- 页面内容兜底表
document_pages (
    id, document_id, page_num,
    markdown_content,
    tables_json,
    images_json,
    artifacts_json
)

-- 原始 Artifacts
artifacts (
    id, document_id, type,  -- table, image, text_chunk
    content_json,
    page_num,
    bbox
)
```

---

## 🔧 配置文件

### `config/config.json`

```json
{
  "providers": {
    "dashscope": {
      "apiKey": "${DASHSCOPE_API_KEY}",
      "apiBase": "https://dashscope.aliyuncs.com/compatible-mode/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "qwen-plus",
      "provider": "dashscope"
    }
  },
  "tools": {
    "restrictToWorkspace": true
  }
}
```

### `data/raw/search_keywords.json`

Stage 3 关键字路由使用的搜索关键词：

```json
{
  "revenue_breakdown": ["营业收入", "主营业务收入", "营收构成"],
  "key_personnel": ["董事", "高管", "核心技术人员"],
  "financial_metrics": ["财务指标", "毛利率", "净利润"]
}
```

---

## 🧪 测试

```bash
# 运行单元测试
pytest tests/

# 测试 PDF 解析
python -m nanobot.ingestion.pipeline test.pdf

# 测试 Hybrid Server
curl http://localhost:5002/health
```

---

## 📚 相关文档

- [OpenDataLoader-PDF](https://github.com/opendataloader/opendataloader-pdf) - Hybrid PDF Parser
- [Vanna AI](https://vanna.ai/) - Text-to-SQL
- [Docling](https://github.com/DS4SD/docling) - Document AI Model
- [nanobot-ai](https://github.com/HKUDS/nanobot) - Core Agent Framework

---

<p align="center">
  <em>Financial Report Analysis with AI Agent 📊</em>
</p>