# nanobot: Financial Report Analysis Agent

<div align="center">
<img src="nanobot_logo.png" alt="nanobot" width="500">
<h1>財報業績分析 AI 智能系統</h1>
<p>
<img src="https://img.shields.io/badge/python-3.11-blue" alt="Python">
<img src="https://img.shields.io/badge/license-MIT-green" alt="License">
<img src="https://img.shields.io/badge/LlamaParse-Cloud_API-orange" alt="LlamaParse">
<img src="https://img.shields.io/badge/Apache_AGE-Graph_DB-blue" alt="Apache AGE">
</p>
</div>

**nanobot** 是一個專門為財務年報/財報業績 PDF 報告進行智能解析和結構化數據提取的 AI Agent 系統。

基於 [nanobot-ai](https://github.com/HKUDS/nanobot) 核心框架，整合 **LlamaParse** (Cloud API) 和 **Apache AGE** (Graph Database)，實現從 PDF 到結構化數據庫的全自動流程。

---

## 版本資訊

| 模組 | 版本 | 說明 |
|------|------|------|
| **Pipeline** | v4.9 | Checkpoint 恢復 + Tool Validation Layer |
| **Schema** | v2.3 | 橋樑表設計、JSONB 動態屬性、規則分配 |
| **Apache AGE** | v1.0 | 圖譜查詢服務（關係查詢、控制權追溯） |

---

## 🌟 Apache AGE 圖數據庫

### License 優勢（商用友好）

| 組件 | License | 商用友好度 |
|------|---------|-----------|
| **Apache AGE** | Apache License 2.0 | ✅ 完全商用友好，無傳染性 |
| **PostgreSQL** | PostgreSQL License | ✅ MIT-like，商用友好 |
| ~~Neo4j Community~~ | ~~GPLv3~~ | ❌ GPL 傳染風險 |

### 為什麼選擇 Apache AGE 而不是 Neo4j？

1. **License 安全**
   - Apache AGE: Apache License 2.0（商用友好）
   - PostgreSQL: PostgreSQL License（MIT-like，商用友好）
   - 無 GPL 傳染風險，適合商業產品

2. **技術優勢**
   - 無需額外數據庫：圖數據存儲在 PostgreSQL 中
   - Cypher 查詢：使用標準 Cypher 語言查詢圖關係
   - PGVector 集成：同一數據庫支持向量搜索和圖查詢

### Apache AGE 工具

| 工具 | 功能 |
|------|------|
| `ApacheAGEQueryTool` | 執行 Cypher 查詢 |
| `GetPersonHoldingsTool` | 查詢某人持股明細 |
| `GetCompanyControllersTool` | 查詢公司控制人 |

---

## 目錄

- [系統架構](#-系統架構)
- [模組結構](#-模組結構)
- [處理流程](#-處理流程)
- [Tools 與 Skills](#-tools-與-skills)
- [數據庫設計](#-數據庫設計)
- [快速啟動](#-快速啟動)

---

## 🔷 系統架構

### 整體架構圖

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        表現層 (Presentation)                         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │
│  │  WebUI   │ │WhatsApp  │ │Telegram  │ │  Slack   │ │ Discord  │  │
│  │ (React)  │ │  Bridge  │ │          │ │          │ │          │  │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        API 層 (API Layer)                            │
│              nanobot/api/server.py (OpenAI 兼容 API)                 │
└──────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        智能層 (Agent Layer)                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐               │
│  │   Loop   │ │  Runner  │ │ Context  │ │  Memory  │               │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘               │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐   │
│  │                    Tool Registry (25+ 工具)                   │   │
│  │  pdf_parser  │  vanna_tool  │  financial  │  filesystem  │ ... │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     數據接入層 (Ingestion Pipeline)                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │Stage 0 │→│Stage 1 │→│Stage 2 │→│Stage 3 │→│Stage 4 │→...      │
│  │ 預處理 │  │ 解析   │  │ 豐富   │  │ 路由   │  │ 提取   │        │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘  └────────────┘        │
└──────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      基礎設施層 (Infrastructure)                      │
│  ┌──────────────────────────┐  ┌──────────────────────────┐  ┌──────────────┐              │
│  │  pdf_core    │  │  llm_core    │  │  db_client   │              │
│  └──────────────────────────┘  └──────────────────────────┘  └──────────────┘              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 處理流程（9-Stage Pipeline）

```
PDF 上傳
    │
    ▼
Stage 1: 解析層 (LlamaParse) → Stage 0: 預處理 (Vision)
    │
    ▼
Stage 0.5: 註冊層 (Hash + Document Registration)
    │
    ▼
Stage 2: 豐富層 (Vision Analysis + Data Enrichment)
    │
    ▼
Stage 3: 關鍵字層 (Keyword Routing)
    │
    ▼
Stage 3.5: 上下文結構構建
    │
    ▼
Stage 4: 智能體提取層 (Tool Calling Extraction)
    │
    ▼
Stage 4.5: 知識圖譜提取層 (Entity Relations)
    │
    ▼
Stage 6: 驗證層 (Data Validation)
    │
    ▼
Stage 7: 向量索引層 (Vector Indexing)
    │
    ▼
Stage 8: 歸檔層 (Archive + Cleanup)
    │
    ▼
數據庫 (PostgreSQL + pgvector + Apache AGE)
```

---

## 🛠️ Tools 與 Skills

### Tool 註冊列表

| 工具 | 功能 |
|------|------|
| `pdf_parser` | PDF 解析 (LlamaParse) |
| `vanna_tool` | Text-to-SQL 查詢 |
| `financial` | 財務數據查詢 |
| `filesystem` | 文件操作 (read/write/edit) |
| `search` | Glob/Grep 搜索 |
| `web` | 網頁搜索/抓取 |
| `apache_age_tool` | 🌟 Apache AGE 圖譜查詢 |
| `db_ingestion_tools` | 數據庫寫入工具 |

---

## 🗄️ 數據庫設計

### 核心表

| 表名 | 功能 |
|------|------|
| `companies` | 公司信息 |
| `documents` | 文檔主表 |
| `document_pages` | 每頁內容兜底表 |
| `financial_metrics` | 財務指標 |
| `revenue_breakdown` | 收入分解 |
| `key_personnel` | 關鍵人員 |
| `shareholding_structure` | 股東結構 |
| `entity_relations` | 實體關係（圖譜） |

---

## 🚀 快速啟動

### Docker 部署

```bash
# 1. 配置環境變量
cp .env.example .env
# 編輯 .env 設置 DASHSCOPE_API_KEY

# 2. 啟動所有服務
docker compose up -d

# 3. 查看服務狀態
docker compose ps

# 4. 訪問 Web UI
open http://localhost:3000
```

### 服務列表

| 服務 | 端口 | 說明 |
|------|------|------|
| `nanobot-webui` | 3000 | Web UI + LlamaParse |
| `nanobot-gateway` | 8081, 18790 | Agent Gateway |
| `postgres-financial` | 5433 | PostgreSQL + pgvector + Apache AGE |

### Apache AGE 初始化

```sql
-- 在 PostgreSQL 中執行
CREATE EXTENSION IF NOT EXISTS age;
SET search_path = ag_catalog, "$user", public;
SELECT create_graph('financial_graph');
```

---

## 📚 相關文檔

- [Pipeline Architecture](docs/pipeline_architecture.md) - Stage 詳細說明
- [Schema ERD](docs/schema_erd.md) - 數據庫關係圖
- [Changelog](CHANGELOG.md) - 版本變更記錄

### 外部資源

- [nanobot-ai](https://github.com/HKUDS/nanobot) - Core Agent Framework
- [Apache AGE](https://age.apache.org/) - Graph Database Extension for PostgreSQL
- [LlamaParse](https://cloud.llamaindex.ai) - PDF Parsing API
- [Vanna AI](https://vanna.ai/) - Text-to-SQL

---

<p align="center">
<em>Financial Report Analysis with AI Agent 🤖📊</em>
<br>
<em>Powered by PostgreSQL + Apache AGE (Commercial-Friendly License)</em>
</p>
