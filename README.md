# nanobot: Financial Report Analysis Agent

<div align="center">
<img src="nanobot_logo.png" alt="nanobot" width="500">
<h1>財務年報分析 AI 代理系統</h1>
<p>
<img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
<img src="https://img.shields.io/badge/license-MIT-green" alt="License">
<img src="https://img.shields.io/badge/LlamaParse-Cloud_API-orange" alt="LlamaParse">
</p>
</div>

**nanobot** 是一個專注於金融年報/財務報告 PDF 解析與結構化數據提取的 AI Agent 系統。

基於 [nanobot-ai](https://github.com/HKUDS/nanobot) 核心框架，結合 **LlamaParse** (Cloud API) 和 **Vanna AI** (Text-to-SQL)，實現從 PDF 到結構化數據庫的完整自動化流程。

---

## 版本資訊

| 模組 | 版本 | 說明 |
|------|------|------|
| **Pipeline** | v4.8 | Stage 1 先行架構，移除 PyMuPDF 依賴 |
| **Schema** | v2.3 | 雙軌制行業、JSONB 動態屬性、完美溯源 |
| **Vanna Service** | v2.3.0 | Text-to-SQL 微服務 |

---

## 目錄

- [系統架構](#-系統架構)
- [專案結構](#-專案結構)
- [處理管道](#-處理管道)
- [Tools 與 Skills](#-tools-與-skills)
- [資料庫設計](#-資料庫設計)
- [設計優缺點分析](#-設計優缺點分析)
- [優化建議](#-優化建議)
- [快速啟動](#-快速啟動)

---

## 🏛️ 系統架構

### 整體架構圖

```
┌─────────────────────────────────────────────────────────────────────┐
│                        表現層 (Presentation)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │  WebUI   │ │WhatsApp  │ │Telegram  │ │  Slack   │ │ Discord  │  │
│  │ (React)  │ │  Bridge  │ │          │ │          │ │          │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        API 層 (API Layer)                            │
│              nanobot/api/server.py (OpenAI 相容 API)                 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        代理層 (Agent Layer)                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│  │   Loop   │ │  Runner  │ │ Context  │ │  Memory  │               │
│  │ (1075行) │ │ (1028行) │ │ (209行)  │ │ (868行)  │               │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Tool Registry (25+ 工具)                   │   │
│  │  pdf_parser  │  vanna_tool  │  financial  │  filesystem  │ ... │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     攝入管道層 (Ingestion Pipeline)                   │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐        │
│  │Stage 0 │→│Stage 1 │→│Stage 2 │→│Stage 3 │→│Stage 4 │→...      │
│  │ 預處理 │  │ 解析   │  │ 豐富化 │  │ 路由   │  │ 提取   │        │
│  └────────┘  └────────┘  └────────┘  └────────┘  └────────┘        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      基礎設施層 (Infrastructure)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  pdf_core    │  │  llm_core    │  │  db_client   │              │
│  │  (1300+行)   │  │   (584行)    │  │  (2018行)    │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

### 核心代理邏輯

**檔案：`nanobot/agent/loop.py`（1075 行）**

代理循環是系統的核心處理引擎，運作流程如下：

```
接收訊息 → Message Bus 收到使用者查詢
    │
    ▼
構建上下文 → ContextBuilder 整合身份、歷史、技能
    │
    ▼
LLM 推理 → AgentRunner 呼叫 LLM Provider
    │
    ▼
工具執行 → ToolRegistry 解析並執行工具調用
    │
    ▼
返回結果 → 回合制對話直到完成
```

**關鍵類別互動：**
- `AgentLoop` - 主循環協調器
- `AgentRunner` - 工具調用執行引擎，支援迭代式 tool calling
- `Context` - 提示詞構建器，組裝系統提示、歷史、技能

---

## 📁 專案結構

```
nanobot/
├── nanobot/                    # 🧠 核心 Python 模組
│   ├── agent/                  # Agent 邏輯層
│   │   ├── loop.py             # 主循環 (LLM ↔ Tool 執行) (1075行)
│   │   ├── runner.py           # 工具執行引擎 (1028行)
│   │   ├── context.py          # Prompt 構建 (209行)
│   │   ├── memory.py           # 持久化記憶 (868行)
│   │   ├── skills.py           # Skills 載入器
│   │   ├── subagent.py         # 子代理管理
│   │   ├── hook.py             # Agent Hook 系統
│   │   ├── autocompact.py      # 自動上下文壓縮
│   │   └── tools/              # 🛠️ Agent Tools (25+ 工具)
│   │       ├── base.py         # Tool 基類
│   │       ├── registry.py     # Tool 註冊表
│   │       ├── pdf_parser.py   # PDF 解析工具 (LlamaParse)
│   │       ├── vanna_tool.py   # Text-to-SQL 工具 (490行)
│   │       ├── financial.py    # 財務數據查詢工具
│   │       ├── filesystem.py   # 檔案操作工具
│   │       ├── search.py       # Glob/Grep 搜尋工具
│   │       ├── web.py          # 網頁搜尋/獲取工具
│   │       ├── message.py      # 訊息工具
│   │       ├── shell.py        # Shell 執行工具
│   │       ├── spawn.py        # 子代理生成
│   │       ├── mcp.py          # MCP 服務連接
│   │       └── cron.py         # 定時任務工具
│   │
│   ├── ingestion/              # 🔄 數據攝入 Pipeline
│   │   ├── pipeline.py         # 主 Pipeline 協調器 (583行)
│   │   ├── base_pipeline.py    # 基類 (模板方法模式) (242行)
│   │   ├── agentic_pipeline.py # Agent-driven Pipeline
│   │   ├── batch_processor.py  # 批次處理器
│   │   ├── agentic_executor.py # Agent 執行器
│   │   ├── stages/             # ⚡ 9-Stage 處理流程
│   │   │   ├── stage0_preprocessor.py      # PDF 預處理 (Vision)
│   │   │   ├── stage0_5_registrar.py       # 文件/公司註冊
│   │   │   ├── stage1_parser.py            # LlamaParse 解析
│   │   │   ├── stage2_enrichment.py        # 圖文關聯/元數據增強
│   │   │   ├── stage3_router.py            # 關鍵字路由
│   │   │   ├── stage3_5_context_builder.py # 結構化上下文建立
│   │   │   ├── stage4_agentic_extractor.py # LLM 結構化提取
│   │   │   ├── stage4_5_kg_extractor.py    # 知識圖譜提取
│   │   │   ├── stage5_vanna_training.py    # Vanna 訓練
│   │   │   ├── stage6_validator.py         # 數據校驗
│   │   │   ├── stage7_vector_indexer.py    # 向量索引
│   │   │   └── stage8_archiver.py          # 歸檔和清理
│   │   ├── extractors/           # 提取器
│   │   │   ├── financial_agent.py
│   │   │   ├── entity_resolver.py
│   │   │   ├── page_classifier.py
│   │   │   └── value_normalizer.py
│   │   ├── parsers/              # 解析器實現
│   │   └── repository/           # 數據庫 Repository
│   │       └── db_client.py      # PostgreSQL 客戶端 (2018行)
│   │
│   ├── core/                    # 📄 核心處理層
│   │   ├── pdf_core.py          # LlamaParse 統一封裝 (1300+行)
│   │   └── llm_core.py          # LLM 統一封裝 (584行)
│   │
│   ├── providers/               # 🤖 LLM Providers
│   │   ├── base.py              # Provider 基類
│   │   ├── registry.py          # Provider 註冊表
│   │   ├── openai_compat_provider.py
│   │   ├── anthropic_provider.py
│   │   ├── azure_openai_provider.py
│   │   ├── github_copilot_provider.py
│   │   └── openai_codex_provider.py
│   │
│   ├── channels/                # 📱 多通道適配器
│   │   ├── base.py              # 通道基類
│   │   ├── manager.py           # 通道管理器
│   │   ├── registry.py          # 通道註冊表
│   │   ├── websocket.py         # WebSocket 通道
│   │   ├── webapi.py            # Web API 通道
│   │   ├── telegram.py
│   │   ├── slack.py
│   │   ├── discord.py
│   │   ├── whatsapp.py
│   │   ├── weixin.py
│   │   ├── feishu.py
│   │   ├── dingtalk.py
│   │   └── msteams.py
│   │
│   ├── session/                 # 💬 對話會話管理
│   │   └── manager.py           # 會話管理器 (390行)
│   │
│   ├── skills/                  # 🎯 Skills (Agent 行為定義)
│   │   ├── financial-analysis/  # 財務分析 Skill
│   │   ├── ingestion/           # 攝入 Skill
│   │   ├── document_indexer/    # 導航地圖 Skill
│   │   ├── memory/              # 記憶管理 Skill
│   │   ├── github/
│   │   ├── summarize/
│   │   └── cron/
│   │
│   ├── config/                  # ⚙️ 配置系統
│   │   ├── schema.py            # Config Schema (Pydantic)
│   │   ├── loader.py            # Config 檔案載入器
│   │   └── paths.py             # 路徑工具
│   │
│   ├── api/                     # HTTP API 服務器
│   │   └── server.py            # OpenAI 相容 API (397行)
│   │
│   ├── utils/                   # 工具函數
│   │   ├── helpers.py
│   │   ├── prompt_templates.py  # Jinja2 提示模板
│   │   ├── document.py
│   │   ├── gitstore.py          # Git 儲存
│   │   └── evaluator.py
│   │
│   └── ...                      # 其他模組 (cli, bus, cron, etc.)
│
├── webui/                       # 🌐 Web UI (React + TypeScript)
│   ├── src/
│   │   ├── components/          # UI 組件
│   │   ├── hooks/               # React Hooks
│   │   ├── providers/           # Context Providers
│   │   ├── lib/
│   │   └── i18n/                # 國際化
│   └── static/
│
├── vanna-service/               # 🧠 Vanna AI (Text-to-SQL)
│   ├── start.py                 # FastAPI 服務器 (1256行)
│   ├── vanna_training.py        # 訓練數據生成
│   ├── ddl.json                 # DDL 知識庫
│   ├── sql_pairs.json           # SQL 示例知識庫
│   └── documentation.json       # 文檔知識庫
│
├── bridge/                      # 🔗 WhatsApp 等橋接 (TypeScript)
│
├── config/                      # ⚙️ 運行時配置
├── data/                        # 📂 數據目錄
│   ├── raw/                     # 原始 PDF / 搜尋關鍵詞
│   ├── uploads/                 # 上傳檔案
│   ├── output/                  # 輸出結果
│   └── vanna/                   # ChromaDB 儲存
│
├── tests/                       # 🧪 測試
├── scripts/                     # 🛠️ 輔助腳本
├── docs/                        # 📚 文檔
│
├── docker-compose.gpu.yml       # 🐳 GPU 版 Compose
├── Dockerfile
├── Dockerfile.gpu
└── pyproject.toml
```

---

## 🔄 處理管道（9-Stage Pipeline）

### Stage 流程圖

**🌟 v4.0 重要更新：Stage 1 先行**

在 v4.0 版本中，Stage 1 (LlamaParse) 先執行，然後 Stage 0 (Vision) 分析 Page 1 的 artifacts。這樣做的好處是：
- LlamaParse 解析後有完整的 Markdown + 圖片
- Vision 提取公司信息更準確

```
PDF 上傳
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: 解析器 (Parser) - LlamaParse Cloud 🌟 最先執行     │
│ ├─ Agentic OCR: LlamaParse Cloud API                        │
│ ├─ 輸出: Markdown + JSON Artifacts                          │
│ ├─ 提取: Tables, Images, Text Chunks                        │
│ ├─ 跨頁表格合併                                              │
│ └─ 創建 raw output 文件夾                                    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 0: 預處理器 (Preprocessor) - Vision 分析 Page 1       │
│ ├─ 分析 LlamaParse 輸出的 Page 1 artifacts                   │
│ ├─ 使用 Vision API 從圖片和 Markdown 提取公司資訊            │
│ ├─ 提取: stock_code, year, name_en, name_zh                 │
│ └─ 🌟 v4.7: 已移除 PyMuPDF 依賴                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 0.5: 註冊器 (Registrar)                               │
│ ├─ 計算文件 Hash                                             │
│ ├─ 文件/公司註冊                                             │
│ ├─ 行業規則判斷 (Rule A: 指數報告 / Rule B: 年報)           │
│ └─ 寫入 companies, documents 表                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: 豐富化 (Enrichment) - RAGAnything                   │
│ ├─ 保存所有頁面到 document_pages 表                          │
│ ├─ Vision 分析圖片（帶精準上下文）                           │
│ ├─ 圖文關聯映射                                              │
│ └─ 防禦性表格修復（PyMuPDF 截圖重解）                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: 路由器 (Router) - 關鍵字掃描                       │
│ ├─ 關鍵字掃描（從 financial_terms_mapping.json 載入）       │
│ ├─ 定位目標頁面                                              │
│ └─ 輸出: 候選頁面列表（告訴 Stage 4 去哪裡找資料）           │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 3.5: 上下文構建器 (Context Builder)                   │
│ ├─ 構建結構化上下文（章節樹、表格上下文）                     │
│ ├─ 使用 LlamaParse items 結構                               │
│ └─ 為 Stage 4 準備輸入                                      │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: 代理提取器 (Agentic Extractor) - Tool Calling      │
│ ├─ 🌟 真正的 Agentic Workflow（Tool Calling Loop）          │
│ ├─ LLM 自己決定調用哪個 Tool                                 │
│ ├─ Revenue Breakdown (收入分解)                             │
│ ├─ Key Personnel (關鍵人員)                                 │
│ ├─ Financial Metrics (財務指標)                             │
│ ├─ Shareholding (股東結構)                                  │
│ ├─ Market Data (市場數據)                                   │
│ └─ 寫入對應的結構化表                                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 4.5: 知識圖譜提取器 (KG Extractor)                    │
│ ├─ 實體關係提取（人物、公司、事件）                          │
│ ├─ 寫入 entity_relations 表                                 │
│ └─ 構建知識圖譜                                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 5: Vanna 訓練 (Training)                              │
│ ├─ Text-to-SQL 訓練                                         │
│ └─ 更新 ChromaDB 向量存儲                                    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 6: 驗證器 (Validator)                                 │
│ ├─ 數據校驗                                                  │
│ ├─ 單位轉換                                                  │
│ └─ 品質檢查                                                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 7: 向量索引器 (Vector Indexer)                        │
│ ├─ 文本切塊 (Semantic Chunking)                             │
│ ├─ 本地 Embedding 生成 (sentence-transformers)              │
│ └─ 寫入向量資料庫                                            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 8: 歸檔器 (Archiver)                                  │
│ ├─ 生成 output.json                                         │
│ ├─ 歸檔處理結果                                              │
│ └─ 清理臨時文件                                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 9: 圖文關聯器 (Image Text Linker)                     │
│ ├─ 建立圖表與解釋文字的關聯                                  │
│ ├─ 寫入 artifact_relations 表                               │
│ └─ 解決「圖表在第 5 頁，解釋在第 50 頁」的問題               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
數據庫 (PostgreSQL + pgvector)
```
```

---

## 🛠️ Tools 與 Skills

### 架構對比

| 類型 | 位置 | 定義方式 | 作用 |
|------|------|----------|------|
| **Tool** | `nanobot/agent/tools/*.py` | Python 函數 | 執行具體操作 |
| **Skill** | `nanobot/skills/*/SKILL.md` | Markdown 指令 | 定義 Agent 行為模式 |

### Tool 註冊表模式

```
ToolRegistry
├── pdf_parser.py     # PDF 解析 (LlamaParse)
├── vanna_tool.py     # Text-to-SQL 查詢 (490行)
├── financial.py      # 財務數據查詢
├── filesystem.py     # 檔案操作 (read/write/edit)
├── search.py         # Glob/Grep 搜尋
├── web.py            # 網頁搜尋/獲取
├── message.py        # 訊息工具
├── shell.py          # Shell 執行
├── spawn.py          # 子代理生成
├── mcp.py            # MCP 服務連接
└── cron.py           # 定時任務
```

### Skill 示例

**`financial-analysis/SKILL.md`:**
```markdown
# Financial Analysis Skill

When user asks about financial reports:
1. Use `parse_pdf` tool to process uploaded PDF
2. Use `query_financial` tool to retrieve structured data
3. Present results in markdown tables
```

---

## 📊 資料庫設計

### Zone 1: 結構化數據表

```sql
-- 結構化提取結果
structured_extraction (
  id, document_id, company_id, year,
  extraction_type, -- revenue_breakdown, key_personnel, financial_metrics
  extracted_data, -- JSON 結構化數據
  source_pages, -- 來源頁碼
  confidence_score
)

-- 財務指標表
financial_metrics (
  id, company_id, year,
  revenue, net_income, total_assets,
  roe, roa, debt_ratio, ...
)

-- 關鍵人員
key_personnel (
  id, company_id, year,
  name_en, name_zh,
  position, committee_membership -- JSONB
)

-- 收入分解
revenue_breakdown (
  id, company_id, year,
  segment_name, -- 原 category
  revenue_amount, -- 原 amount
  percentage
)
```

### Zone 2: 兜底表（所有頁面）

```sql
-- 頁面內容兜底表
document_pages (
  id, document_id, page_num,
  markdown_content,
  tables_json,
  images_json,
  artifacts_json
)

-- 原始 Artifacts
artifacts (
  id, document_id, type, -- table, image, text_chunk
  content_json,
  page_num,
  bbox
)
```

### 雙軌制行業系統

| 規則 | 觸發條件 | 行業來源 | 行為 |
|------|----------|----------|------|
| **Rule A** | 指數報告（標題含 Index、恒生指數、HSI） | `confirmed_industry` | `is_industry_confirmed = TRUE` |
| **Rule B** | 年度報告，無單一行業主題 | `ai_extracted_industries` (JSONB) | `is_industry_confirmed = FALSE` |

---

## ⚖️ 設計優缺點分析

### 優點（Strengths）

#### ✅ 模組化架構
- **清晰的關注點分離**：代理、管道、工具、通道各自獨立
- **高度內聚、低耦合**：每個模組職責明確
- **易於擴展**：新增工具/通道只需實現註冊

#### ✅ 多通道支援
- 支援 Web、WhatsApp、Telegram、Slack、Discord、Feishu、DingTalk、Line 等
- 使用**配接器模式**統一接口

#### ✅ 強大的 PDF 處理能力
- LlamaParse 雲端解析（高準確度）
- 9 階段處理管道，分工明確
- Vision API 輔助封面識別

#### ✅ 靈活的 LLM 支援
- 支援 OpenAI、Anthropic、Azure OpenAI、GitHub Copilot、DashScope、Ollama 等
- **Provider 註冊表模式**便於擴展

#### ✅ 技能系統
- Markdown 定義行為，易於編寫和維護
- 熱重載支援，無需重啟

#### ✅ Text-to-SQL 能力
- Vanna AI 集成，自然語言轉 SQL
- 支援複雜財務分析查詢

#### ✅ 記憶系統
- 基於檔案的對話歷史（JSONL）
- Consolidator 進行 token 優化
- AutoCompact 自動上下文壓縮
- Dream 背景記憶處理

### 缺點（Weaknesses）

#### ❌ 過於複雜的架構
- **過度工程化**：大量抽象層和間接引用
- 檔案行數過大（`loop.py` 1075 行、`db_client.py` 2018 行）
- 新進開發者學習曲線陡峭

#### ❌ 錯誤處理不一致
- 不同模組的錯誤處理方式各異
- 缺乏統一的異常層級體系

#### ❌ 測試覆蓋不足
- 從目錄結構看，測試相對薄弱
- 關鍵邏輯缺乏單元測試

#### ❌ 性能考量
- 同步檔案 I/O 在高併發下可能成為瓶頸
- Pipeline 每個階段都是順序執行，沒有並行優化
- LLM 調用缺乏批次處理優化

#### ❌ 配置管理混亂
- 多處配置（YAML、ENV、程式碼常量）
- 缺乏集中的配置驗證

#### ❌ 文檔不足
- 缺乏 API 文檔和架構圖
- SKILL.md 描述有限

#### ❌ 單點故障風險
- Vanna 服務與主系統耦合
- Pipeline 某階段失敗會影響整個流程

---

## 🚀 優化建議

### 準確性提升

#### 1. 增加驗證層級

```python
# 在 stage4_agentic_extractor.py 中增加交叉驗證
class CrossValidator:
    def validate_extraction(self, extracted: dict, raw_text: str) -> ValidationResult:
        # 使用多個 LLM 進行獨立的結構化提取
        # 比較結果並標記不一致之處
        pass
```

#### 2. 改善 PDF 解析品質

```python
# 在 pdf_core.py 中增加表格結構恢復
class TableStructureRecovery:
    def recover_table(self, raw_elements: list) -> List[List[str]]:
        # 使用視覺模型識別表格邊界
        # 還原行列結構
        pass
```

#### 3. 增強知識圖譜提取

```python
# 在 stage4_5_kg_extractor.py 中
class RelationExtractor:
    def extract_with_confidence(self, text: str) -> List[Triple]:
        # 使用鏈式思考提示
        # 輸出每個三元組的置信度
        pass

    def filter_low_confidence(self, triples: List[Triple], threshold: float = 0.8):
        # 過濾低置信度關係
        pass
```

### 效能提升

#### 1. Pipeline 並行化

```python
# 在 pipeline.py 中使用並行階段
class ParallelPipeline:
    async def process(self, pdf_path: str):
        # Stage 0 和 Stage 0.5 可以並行
        stage_0_task = self.stage_0.process(pdf_path)
        stage_0_5_task = self.stage_0_5.process(pdf_path)
        results = await asyncio.gather(stage_0_task, stage_0_5_task)

        # Stage 1 完成後，2、3、4 可以並行
        # ...
```

#### 2. 批次處理優化

```python
# 在 llm_core.py 中增加批次處理
class BatchLLMCaller:
    async def batch_complete(self, prompts: List[str], batch_size: int = 10):
        # 批次發送請求減少 API 延遲
        # 使用 async 並發控制
        pass
```

#### 3. 快取優化

```python
# 在 pdf_core.py 中增強快取
class SemanticCache:
    def get_with_fingerprint(self, pdf_path: str, content_hash: str):
        # 不僅基於路徑，還基於內容指紋
        # 檢測 PDF 文字/結構變化
        pass
```

#### 4. 非同步資料庫操作

```python
# 在 db_client.py 中全面使用 asyncpg
class AsyncDBClient:
    async def batch_insert(self, records: List[dict]):
        # 使用 asyncpg 的 copy_records_to_table
        # 批次插入提升效能
        pass
```

#### 5. 記憶體優化

```python
# 在 pdf_core.py 中使用流式處理
class StreamingPDFParser:
    def parse_streaming(self, pdf_path: str, page_handler: Callable):
        # 流式處理頁面，避免一次性載入
        # 分頁提交給 LLM
        pass
```

### 架構簡化建議

| 問題 | 建議 |
|------|------|
| 過大的單一檔案 | 拆分 `loop.py`、`db_client.py` 為協作者模式 |
| 過多抽象層 | 減少繼承深度，使用組合而非繼承 |
| 複雜的階段流程 | 引入工作流引擎（如 Prefect）管理複雜依賴 |

### 監控與可觀測性

```python
# 新增監控層
class PipelineMonitor:
    def track_latency(self, stage: str, duration: float):
        # 追蹤每個階段延遲
        pass

    def track_accuracy(self, stage: str, accuracy: float):
        # 追蹤提取準確度
        pass

    def alert_on_failure(self, stage: str, error: Exception):
        # 失敗告警
        pass
```

---

## 🚀 快速啟動

### Docker GPU 版（推薦）

```bash
# 1. 配置環境變量
cp .env.example .env
# 編輯 .env 設置 DASHSCOPE_API_KEY

# 2. 啟動所有服務
docker compose -f docker-compose.gpu.yml up -d

# 3. 查看狀態
docker compose -f docker-compose.gpu.yml ps

# 4. 訪問 Web UI
open http://localhost:3000
```

### 服務列表

| 服務 | 端口 | 說明 |
|------|------|------|
| `nanobot-webui` | 3000 | Web UI + LlamaParse |
| `nanobot-gateway` | 8081, 18790 | Agent Gateway |
| `postgres-financial` | 5433 | PostgreSQL + pgvector |
| `vanna-service` | 8082 | Vanna AI (內部) |

---

## 🧪 測試

```bash
# 運行單元測試
pytest tests/

# 測試 PDF 解析
python -m nanobot.ingestion.pipeline test.pdf

# 測試 LlamaParse
curl http://localhost:5002/health
```

---

## 📚 相關文檔

### 專案文檔

- [Pipeline Architecture](docs/pipeline_architecture.md) - Stage 職責詳解
- [Code Review 2026-04-18](docs/CODE_REVIEW_2026-04-18.md) - 程式碼審查報告
- [Schema ERD](docs/schema_erd.md) - 資料庫關係圖
- [Changelog](CHANGELOG.md) - 版本變更日誌

### 外部資源

- [OpenDataLoader-PDF](https://github.com/opendataloader/opendataloader-pdf) - Hybrid PDF Parser
- [Vanna AI](https://vanna.ai/) - Text-to-SQL
- [Docling](https://github.com/DS4SD/docling) - Document AI Model
- [nanobot-ai](https://github.com/HKUDS/nanobot) - Core Agent Framework

---

<p align="center">
<em>Financial Report Analysis with AI Agent 📊</em>
</p>