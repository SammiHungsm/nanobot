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