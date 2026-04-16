# Nanobot Project Memory - Complete File Reference

**Project Root**: `C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot`

**Description**: Enterprise AI Agent System for Financial Document Processing

This memory provides a complete reference of every file in the project, its purpose, relationships, and rationale.

---

## 📁 Directory Structure Overview

```
nanobot/
├── nanobot/                     # 🧠 Core Python Package
│   ├── agent/                   # Agent Loop, Tools, Skills, Memory
│   ├── api/                     # REST API Server
│   ├── bus/                     # Message Bus (Event Queue)
│   ├── channels/                # Multi-channel Support (Telegram, Discord, etc.)
│   ├── cli/                     # Command-Line Interface
│   ├── command/                 # Command Router & Built-in Commands
│   ├── config/                  # Configuration Schema & Loader
│   ├── core/                    # PDF & LLM Core Utilities
│   ├── cron/                    # Cron Service for Scheduled Tasks
│   ├── heartbeat/               # Heartbeat Service
│   ├── ingestion/               # 📄 PDF Ingestion Pipeline (7 Stages)
│   ├── providers/               # LLM Provider Implementations
│   ├── security/                # Security Utilities
│   ├── session/                 # Session Management
│   ├── skills/                  # Skill Definitions (SKILL.md)
│   ├── templates/               # Prompt Templates
│   └── utils/                   # General Utilities
│
├── scripts/                     # Utility Scripts
├── tests/                       # Test Suite
├── data/                        # Data Directory (Raw, Uploads, Output)
├── storage/                     # Database Schema (SQL)
├── webui/                       # Web Frontend (FastAPI + React)
├── vanna-service/               # Text-to-SQL Service
└── docker-compose.yml           # Docker Orchestration
```

---

## 🧠 Core Package (`nanobot/nanobot/`)

### Entry Points

| File | Purpose | Relationships | Why |
|------|---------|---------------|-----|
| `__main__.py` | Module entry point (`python -m nanobot`) | → `cli/commands.py:app` | Allows running as Python module |
| `nanobot.py` | Main Nanobot class | → `agent/loop.py`, `channels/manager.py`, `config/loader.py` | Top-level orchestrator for CLI and API modes |
| `__init__.py` | Package initialization, version, logo | — | Defines package metadata |

### Agent System (`nanobot/agent/`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `loop.py` | **Agent Loop** - Core processing engine | `AgentLoop`, `_LoopHook` | → `context.py`, `memory.py`, `tools/registry.py`, `providers/base.py` | Executes the main AI reasoning loop: Receive → Context → LLM → Tools → Respond |
| `context.py` | **Context Builder** - Constructs prompts | `ContextBuilder` | → `skills.py`, `memory.py`, `templates/` | Builds the full prompt with history, skills, memory for each LLM call |
| `memory.py` | **Memory System** - Long-term memory | `Consolidator`, `Dream` | → `session/manager.py`, `templates/agent/dream_*.md` | Implements Dream (periodic consolidation) and short-term memory |
| `skills.py` | **Skills Loader** - Loads SKILL.md files | `SkillsLoader` | → `skills/**/*.md` | Dynamically loads skill definitions into prompts |
| `runner.py` | **Agent Runner** - Execution spec | `AgentRunSpec`, `AgentRunner` | → `loop.py` | Defines how agent runs are structured and executed |
| `subagent.py` | **Subagent Manager** - Delegation | `SubagentManager` | → `loop.py`, `bus/events.py` | Manages spawning and coordinating subagents for parallel tasks |
| `hook.py` | **Hook System** - Lifecycle hooks | `AgentHook`, `CompositeHook` | → `loop.py` | Allows plugins to intercept agent lifecycle events |
| `tools/` | **Tool System** - 20+ built-in tools | See below | → All external APIs | Provides capabilities like file ops, web search, shell, DB, etc. |

#### Tools (`nanobot/agent/tools/`)

| File | Purpose | Key Tools | Relationships | Why |
|------|---------|-----------|---------------|-----|
| `registry.py` | Tool registry & execution | `ToolRegistry` | ← All tool files | Central registry for dynamic tool management |
| `base.py` | Tool base class | `Tool` | ← All tool files | Defines interface: `name`, `description`, `execute()` |
| `filesystem.py` | File operations | `ReadFileTool`, `WriteFileTool`, `EditFileTool`, `ListDirTool` | — | Safe file manipulation with workspace restrictions |
| `shell.py` | Shell execution | `ExecTool` | → `config/schema.py:ExecToolConfig` | Run shell commands with timeout and sandbox options |
| `search.py` | Code search | `GlobTool`, `GrepTool` | — | Search files by pattern or content |
| `web.py` | Web operations | `WebSearchTool`, `WebFetchTool` | → `config/schema.py:WebToolsConfig` | Web search (DuckDuckGo, Brave, Tavily) and page fetching |
| `spawn.py` | Subagent spawning | `SpawnTool` | → `subagent.py` | Spawn background agents for parallel work |
| `message.py` | Message sending | `MessageTool` | → `bus/events.py` | Send messages to channels |
| `cron.py` | Cron management | `CronTool` | → `cron/service.py` | Create, list, toggle cron jobs |
| `mcp.py` | MCP integration | `MCPTool` | → MCP servers | Connect to Model Context Protocol servers |
| `vanna_tool.py` | Vanna Text-to-SQL | `VannaTool` | → `vanna-service/` | Generate SQL from natural language |
| `financial.py` | Financial DB queries | `QueryFinancialDatabaseTool` | → `ingestion/repository/db_client.py` | Query financial metrics database |
| `pdf_parser.py` | PDF parsing | `ParseFinancialPdfTool` | → `core/pdf_core.py` | Parse PDFs using LlamaParse |
| `entity_resolver.py` | Entity resolution | `ResolveEntityTool` | → `ingestion/extractors/entity_resolver.py` | Resolve company name variations |
| `multimodal_rag.py` | RAG search | `MultimodalRagTool` | → Vector DB | Search across text, tables, images |
| `dynamic_schema_tools.py` | Dynamic schema | `GetDbSchemaTool` | → `ingestion/repository/db_client.py` | Get database schema dynamically |
| `db_ingestion_tools.py` | DB ingestion | `SmartInsertDocumentTool`, `UpdateDocumentStatusTool` | → `ingestion/repository/db_client.py` | Insert documents with industry rules (A/B) |
| `register_all.py` | Tool registration | `register_all_tools()` | ← All tool files | Registers all built-in tools |

### Configuration (`nanobot/config/`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `schema.py` | **Pydantic Schema** - Config structure | `Config`, `AgentDefaults`, `ProviderConfig`, `ChannelsConfig` | ← All modules | Defines validated configuration structure with camelCase/snake_case support |
| `loader.py` | Config loader | `load_config()`, `resolve_config_env_vars()` | → `schema.py` | Loads `config.json` with env var interpolation |
| `paths.py` | Path management | `get_workspace_path()`, `get_config_path()` | — | Centralized path resolution |

### LLM Providers (`nanobot/providers/`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `base.py` | **Provider Interface** | `LLMProvider`, `LLMResponse`, `ToolCallRequest` | ← All providers | Abstract base class for all LLM providers |
| `registry.py` | Provider registry | `PROVIDERS`, `ProviderSpec`, `find_by_name()` | ← All providers | Registry of 20+ providers with keyword matching |
| `openai_compat_provider.py` | OpenAI-compatible | `OpenAICompatProvider` | → `base.py` | Supports OpenAI, DashScope, Ollama, vLLM, etc. |
| `anthropic_provider.py` | Anthropic Claude | `AnthropicProvider` | → `base.py` | Supports Claude with thinking blocks |
| `azure_openai_provider.py` | Azure OpenAI | `AzureOpenAIProvider` | → `openai_compat_provider.py` | Azure-specific authentication |
| `github_copilot_provider.py` | GitHub Copilot | `GithubCopilotProvider` | → `openai_compat_provider.py` | OAuth-based Copilot integration |
| `openai_codex_provider.py` | OpenAI Codex | `OpenAICodexProvider` | → `openai_compat_provider.py` | OAuth-based Codex integration |
| `transcription.py` | Voice transcription | `TranscriptionProvider` | → `config/schema.py` | Groq/OpenAI Whisper for voice |

### Core Utilities (`nanobot/core/`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `pdf_core.py` | **PDF Parser** - LlamaParse wrapper | `PDFParser`, `PDFParseResult` | → `ingestion/stages/stage1_parser.py` | Unified PDF parsing with image download and raw output caching |
| `llm_core.py` | **LLM Client** - Unified interface | `UnifiedLLMCore`, `llm_core`, `detect_provider()` | → `providers/registry.py`, `config/loader.py` | Single interface for chat/vision across all providers |

### Ingestion Pipeline (`nanobot/ingestion/`)

**7-Stage PDF Processing Pipeline**:

| Stage | File | Purpose | Relationships | Why |
|-------|------|---------|---------------|-----|
| **Orchestrator** | `pipeline.py` | Main coordinator | → All stages, `extractors/`, `repository/db_client.py` | Coordinates 7-stage pipeline with progress tracking |
| **Base** | `base_pipeline.py` | Base class with LlamaParse | → `core/pdf_core.py` | Provides common functionality for all pipelines |
| **Stage 0** | `stages/stage0_preprocessor.py` | PDF validation & batching | → `pipeline.py` | Validates PDF, splits large files into batches |
| **Stage 1** | `stages/stage1_parser.py` | **LlamaParse** parsing | → `core/pdf_core.py` | Calls LlamaParse API, saves raw output to avoid re-processing fees |
| **Stage 2** | `stages/stage2_enrichment.py` | Enrichment | → `pipeline.py` | Enhances metadata, links images/tables |
| **Stage 3** | `stages/stage3_router.py` | Keyword routing | → `utils/keyword_manager.py` | Uses keywords to identify relevant pages |
| **Stage 4** | `stages/stage4_extractor.py` | **Agentic Extraction** | → `core/llm_core.py`, `extractors/financial_agent.py` | LLM extracts structured data (Revenue, Personnel, Metrics) |
| **Stage 5** | `stages/stage5_agentic_writer.py` | Agentic writing | → `agentic_pipeline.py` | AI Agent analyzes first pages, extracts entities |
| **Stage 6** | `stages/stage6_vanna_training.py` | Vanna training | → `vanna-service/` | Trains Vanna Text-to-SQL on extracted data |

**Extractors** (`nanobot/ingestion/extractors/`):

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `financial_agent.py` | Financial data agent | `FinancialAgent` | → `core/llm_core.py` | Specialized agent for financial extraction |
| `page_classifier.py` | Page classification | `PageClassifier` | → `core/llm_core.py` | Classifies pages by type (table, text, chart) |
| `entity_resolver.py` | Entity resolution | `EntityResolver` | → `agent/tools/entity_resolver.py` | Resolves company names, stock codes |
| `value_normalizer.py` | Value normalization | `ValueNormalizer` | — | Normalizes numbers, dates, currencies |
| `prompts.py` | Extraction prompts | Prompt templates | → `stage4_extractor.py` | Centralized prompt definitions |

**Utils** (`nanobot/ingestion/utils/`):

| File | Purpose | Key Functions | Relationships | Why |
|------|---------|---------------|---------------|-----|
| `keyword_manager.py` | Keyword management | `KeywordManager` | → `stage3_router.py` | Manages `search_keywords.json` for routing |
| `table_merger.py` | Cross-page table merging | `cross_page_merger` | → `stage2_enrichment.py` | Merges tables split across pages |

**Validators** (`nanobot/ingestion/validators/`):

| File | Purpose | Key Functions | Relationships | Why |
|------|---------|---------------|---------------|-----|
| `math_rules.py` | Mathematical validation | Validation rules | → `stage4_extractor.py` | Validates extracted numbers for consistency |

**Repository** (`nanobot/ingestion/repository/`):

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `db_client.py` | **Database Client** - PostgreSQL | `DBClient` | → All stages, `extractors/` | Connection pool, transaction management, schema caching |

### Channels (`nanobot/channels/`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `manager.py` | **Channel Manager** - Coordinator | `ChannelManager` | → All channel files | Manages lifecycle of all enabled channels |
| `base.py` | Base channel class | `BaseChannel` | ← All channels | Defines interface: `start()`, `stop()`, `send()`, `send_delta()` |
| `registry.py` | Channel discovery | `discover_all()` | ← All channels | Auto-discovers channels via pkgutil/entry_points |
| `webapi.py` | **REST API** - Web UI backend | `WebAPIChannel` | → `bus/events.py` | FastAPI server with `/api/chat` and `/api/stream` |
| `websocket.py` | WebSocket channel | `WebSocketChannel` | → `bus/events.py` | Real-time bidirectional communication |
| `telegram.py` | Telegram Bot | `TelegramChannel` | → `base.py` | Telegram integration |
| `discord.py` | Discord Bot | `DiscordChannel` | → `base.py` | Discord integration |
| `feishu.py` | Feishu/Lark | `FeishuChannel` | → `base.py` | Enterprise chat (Feishu/Lark) |
| `dingtalk.py` | DingTalk | `DingTalkChannel` | → `base.py` | Enterprise chat (DingTalk) |
| `slack.py` | Slack Bot | `SlackChannel` | → `base.py` | Slack integration |
| `whatsapp.py` | WhatsApp | `WhatsAppChannel` | → `base.py` | WhatsApp Business API |
| `wecom.py` | WeCom | `WeComChannel` | → `base.py` | WeChat Work integration |
| `weixin.py` | WeChat | `WeixinChannel` | → `base.py` | WeChat Official Account |
| `qq.py` | QQ | `QQChannel` | → `base.py` | QQ integration |
| `email.py` | Email | `EmailChannel` | → `base.py` | Email-based interaction |
| `matrix.py` | Matrix | `MatrixChannel` | → `base.py` | Matrix protocol |
| `mochat.py` | MoChat | `MoChatChannel` | → `base.py` | MoChat integration |

### Session & Memory (`nanobot/session/`, `nanobot/agent/memory.py`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `manager.py` | Session management | `SessionManager`, `Session` | → `agent/loop.py` | Manages conversation history per channel/chat_id |
| `memory.py` | Memory consolidation | `Consolidator`, `Dream` | → `templates/agent/dream_*.md` | Periodic memory consolidation (Dream) every 2h |

### Bus & Events (`nanobot/bus/`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `events.py` | Event definitions | `InboundMessage`, `OutboundMessage` | ← All channels, `agent/loop.py` | Defines message structure for pub/sub |
| `queue.py` | Message queue | `MessageBus` | → `channels/manager.py`, `agent/loop.py` | Async pub/sub message bus |

### CLI (`nanobot/cli/`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `commands.py` | **CLI Commands** - Typer app | `app`, `_print_agent_response()` | → `agent/loop.py`, `stream.py` | Main CLI with interactive mode, streaming |
| `stream.py` | Streaming renderer | `StreamRenderer`, `ThinkingSpinner` | → `commands.py` | Renders streaming output with spinners |
| `models.py` | CLI models | Pydantic models | → `commands.py` | Request/response models |
| `onboard.py` | Onboarding flow | Onboarding logic | → `config/loader.py` | First-run setup wizard |

### Command System (`nanobot/command/`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `router.py` | Command router | `CommandRouter` | → `builtin.py` | Routes `/command` messages |
| `builtin.py` | Built-in commands | `/dream`, `/memory`, `/restart` | → `agent/memory.py`, `utils/restart.py` | Built-in slash commands |

### Cron System (`nanobot/cron/`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `service.py` | Cron scheduler | `CronService` | → `types.py`, `agent/tools/cron.py` | Runs scheduled jobs (Dream, Heartbeat) |
| `types.py` | Cron types | `CronSchedule` | → `service.py` | Defines schedule types (cron, interval) |

### Heartbeat (`nanobot/heartbeat/`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `service.py` | Heartbeat service | `HeartbeatService` | → `bus/events.py` | Periodic "I'm alive" messages to channels |

### API Server (`nanobot/api/`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `server.py` | OpenAI-compatible API | FastAPI app | → `agent/loop.py` | Exposes agent as OpenAI-compatible API |

### Security (`nanobot/security/`)

| File | Purpose | Key Classes | Relationships | Why |
|------|---------|-------------|---------------|-----|
| `network.py` | Network security | Security utilities | — | Validates URLs, prevents SSRF |

### Skills (`nanobot/skills/`)

Each skill is defined by a `SKILL.md` file:

| Skill | Purpose | Tools Used | Why |
|-------|---------|------------|-----|
| `financial-analysis/` | Financial analysis | `query_financial_database`, `parse_financial_pdf`, `search_documents` | Analyze annual reports with 100% accuracy |
| `ingestion/` | Document ingestion | `smart_insert_document`, `update_document_status` | Industry assignment rules (A/B) |
| `memory/` | Memory management | `/dream`, `/memory` | Manage long-term memory |
| `skill-creator/` | Create new skills | File ops | Scaffold new skills |
| `document_indexer/` | Document indexing | Search tools | Build document indexes |
| `github/` | GitHub integration | Web tools | GitHub operations |
| `cron/` | Cron management | `CronTool` | Schedule tasks |
| `clawhub/` | ClawHub integration | — | ClawHub platform |
| `summarize/` | Summarization | — | Summarize documents |
| `weather/` | Weather queries | Web tools | Weather information |
| `tmux/` | Tmux control | Shell tools | Terminal multiplexer |

### Templates (`nanobot/templates/`)

| File | Purpose | Used By | Why |
|------|---------|---------|-----|
| `agent/identity.md` | Agent identity prompt | `context.py` | Defines agent persona |
| `agent/dream_phase1.md` | Dream Phase 1 prompt | `memory.py` | Memory consolidation |
| `agent/dream_phase2.md` | Dream Phase 2 prompt | `memory.py` | Memory refinement |
| `agent/evaluator.md` | Evaluator prompt | `utils/evaluator.py` | Quality evaluation |
| `agent/skills_section.md` | Skills section | `skills.py` | Injects skills into prompt |
| `agent/subagent_system.md` | Subagent system prompt | `subagent.py` | Subagent coordination |
| `TOOLS.md` | Tool descriptions | `context.py` | Tool documentation |
| `USER.md` | User preferences | `context.py` | User-specific context |
| `SOUL.md` | Core identity | `context.py` | Agent's core identity |
| `HEARTBEAT.md` | Heartbeat message | `heartbeat/service.py` | Periodic status |

### Utilities (`nanobot/utils/`)

| File | Purpose | Key Functions | Relationships | Why |
|------|---------|---------------|---------------|-----|
| `helpers.py` | General helpers | `truncate_text()`, `strip_think()` | ← All modules | Common utilities |
| `path.py` | Path utilities | Path manipulation | — | Cross-platform path handling |
| `restart.py` | Restart logic | `should_show_restart_notice()` | → `cli/commands.py` | Graceful restarts |
| `runtime.py` | Runtime checks | Platform detection | — | Runtime environment info |
| `evaluator.py` | Quality evaluator | Evaluation logic | → `templates/agent/evaluator.md` | Evaluate agent output quality |
| `gitstore.py` | Git storage | Git operations | — | Version control integration |
| `prompt_templates.py` | Prompt templates | Template rendering | — | Centralized prompt management |
| `tool_hints.py` | Tool hints | Hint generation | → `agent/loop.py` | Generate tool call hints |
| `searchusage.py` | Search usage tracking | Usage statistics | — | Track search API usage |

---

## 📄 Scripts

| File | Purpose | Why |
|------|---------|-----|
| `init_mongodb.py` | MongoDB initialization | Legacy MongoDB setup |
| `resume_pipeline.py` | Resume interrupted pipeline | Recovery from failures |

---

## 🧪 Tests

Comprehensive test suite organized by module:

| Directory | Purpose | Coverage |
|-----------|---------|----------|
| `tests/agent/` | Agent tests | Loop, memory, skills, tools, session |
| `tests/channels/` | Channel tests | All channel implementations |
| `tests/cli/` | CLI tests | Commands, streaming |
| `tests/config/` | Config tests | Schema validation, env interpolation |
| `tests/cron/` | Cron tests | Scheduling, timezone |
| `tests/providers/` | Provider tests | All LLM providers |
| `tests/command/` | Command tests | Built-in commands |

---

## 🗄️ Database Schema (`storage/`)

| File | Purpose | Why |
|------|---------|-----|
| `init_complete.sql` | Complete schema | PostgreSQL + pgvector + pg_trgm |

**Key Tables**:
- `companies` - Company master data (dual-track industry)
- `documents` - Document management
- `document_pages` - PDF page content with embeddings
- `financial_metrics` - Financial metrics (EAV + JSONB)
- `revenue_breakdown` - Revenue breakdown
- `key_personnel` - Key personnel
- `entity_relations` - Entity relationships
- `vanna_training_data` - Vanna training data

---

## 🌐 WebUI (`webui/`)

| File | Purpose | Why |
|------|---------|-----|
| `app/main.py` | FastAPI backend | Serves React frontend + API proxy |
| `frontend/` | React frontend | User interface |

---

## 🧠 Vanna Service (`vanna-service/`)

| File | Purpose | Why |
|------|---------|-----|
| `start.py` | Vanna Text-to-SQL service | Train and query SQL generation |

---

## 🐳 Docker (`docker-compose.yml`)

| Service | Port | Purpose |
|---------|------|---------|
| `postgres-financial` | 5433 | PostgreSQL + pgvector |
| `nanobot-gateway` | 18790 | Agent gateway |
| `nanobot-webui` | 3000 | Web frontend |
| `vanna-service` | 8000 | Text-to-SQL |
| `ingestion-worker` | - | PDF processing worker |

---

## 🔑 Key Design Patterns

### 1. **Message Bus Architecture**
```
Channel → InboundMessage → MessageBus → AgentLoop → OutboundMessage → Channel
```

### 2. **7-Stage Ingestion Pipeline**
```
PDF → Stage0 (Preprocess) → Stage1 (LlamaParse) → Stage2 (Enrich) → 
Stage3 (Route) → Stage4 (Extract) → Stage5 (Agentic Write) → Stage6 (Vanna Train)
```

### 3. **Provider System**
```
config.json → ProviderConfig → LLMProvider (OpenAICompat/Anthropic) → LLMResponse
```

### 4. **Tool System**
```
SKILL.md → Tool Definition → ToolRegistry → Tool.execute() → Result
```

### 5. **Memory Consolidation**
```
Session History → Dream (every 2h) → Consolidated Memory → Long-term Storage
```

### 6. **Industry Assignment Rules**
- **Rule A**: Index reports with confirmed industry → All constituents get same industry
- **Rule B**: Annual reports → AI suggests multiple industries per company

---

## 📊 Data Flow Examples

### Example 1: User Uploads PDF

```
1. User uploads PDF via WebUI
   ↓
2. WebAPI Channel → InboundMessage → MessageBus
   ↓
3. AgentLoop receives message
   ↓
4. Agent calls `parse_financial_pdf` tool
   ↓
5. PDF Core (LlamaParse) parses PDF
   ↓
6. Stage 4 Extractor extracts structured data
   ↓
7. DB Client writes to PostgreSQL
   ↓
8. Agent responds with summary
```

### Example 2: User Asks Financial Question

```
1. User: "What was Tencent's revenue in 2023?"
   ↓
2. Agent analyzes intent → Requires exact numbers
   ↓
3. Agent calls `query_financial_database` tool
   ↓
4. DB Client queries `financial_metrics` table
   ↓
5. Agent formats response with citations
   ↓
6. Response sent to user
```

### Example 3: Dream Memory Consolidation

```
1. Cron Service triggers Dream every 2h
   ↓
2. Dream Phase 1: Summarize recent sessions
   ↓
3. Dream Phase 2: Refine and extract insights
   ↓
4. Consolidated memory saved to file
   ↓
5. Future sessions include consolidated memory
```

---

## 🎯 Key Configuration Files

### `config.json` Structure

```json
{
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "vision_model": "gpt-4o",
      "provider": "auto",
      "max_tokens": 8192,
      "context_window_tokens": 65536,
      "max_tool_iterations": 200,
      "dream": {
        "interval_h": 2,
        "max_batch_size": 20
      }
    }
  },
  "providers": {
    "anthropic": { "api_key": "..." },
    "openai": { "api_key": "..." },
    "dashscope": { "api_key": "..." }
  },
  "channels": {
    "webapi": { "enabled": true, "port": 8081 },
    "telegram": { "enabled": false }
  },
  "tools": {
    "web": { "enable": true },
    "exec": { "enable": true }
  }
}
```

### `.env` Variables

```bash
# LLM
DASHSCOPE_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx

# Database
DATABASE_URL=postgresql://user:pass@host:5432/db

# LlamaParse
LLAMA_CLOUD_API_KEY=llx-xxx
LLAMAPARSE_TIER=agentic

# Data Paths
DATA_DIR=/app/data/raw
```

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -e .

# 2. Configure
cp config.json.example config.json
# Edit config.json with API keys

# 3. Run CLI
nanobot

# 4. Or run API server
nanobot serve

# 5. Or run with Docker
docker-compose up -d
```

---

## 📝 File Relationships Summary

### Core Dependencies

```
nanobot.py (main)
├── agent/loop.py (AgentLoop)
│   ├── context.py (ContextBuilder)
│   │   ├── skills.py → skills/**/*.md
│   │   ├── memory.py → templates/agent/dream_*.md
│   │   └── templates/
│   ├── tools/registry.py → tools/*.py
│   ├── providers/base.py → providers/*.py
│   └── session/manager.py
│
├── channels/manager.py
│   └── channels/*.py (webapi, telegram, discord, etc.)
│
├── config/loader.py → config/schema.py
│
└── ingestion/pipeline.py
    ├── stages/stage*.py
    ├── extractors/*.py
    ├── utils/*.py
    └── repository/db_client.py
```

### Data Flow

```
User Input → Channel → MessageBus → AgentLoop → LLM → Tools → External APIs/DB
                ↑                                              ↓
                └────────────── Response ←─────────────────────┘
```

---

## 🎓 Key Concepts

1. **Agent Loop**: The core reasoning cycle (Receive → Context → LLM → Tools → Respond)
2. **Skills**: Markdown-defined capabilities that extend agent knowledge
3. **Tools**: Executable functions the agent can call (file ops, web, DB, etc.)
4. **Dream**: Periodic memory consolidation (every 2h by default)
5. **Industry Rules**: Rule A (confirmed) vs Rule B (AI-extracted) for company classification
6. **LlamaParse**: Cloud PDF parser with raw output caching to avoid re-processing fees
7. **Vanna AI**: Text-to-SQL training on extracted financial data
8. **Multi-channel**: Support for 15+ chat platforms (Telegram, Discord, Feishu, etc.)

---

## 🔧 Maintenance Notes

- **Adding a new tool**: Create file in `agent/tools/`, register in `register_all.py`
- **Adding a new channel**: Create file in `channels/`, implement `BaseChannel` interface
- **Adding a new provider**: Create file in `providers/`, implement `LLMProvider` interface, add to `registry.py`
- **Adding a new skill**: Create folder in `skills/` with `SKILL.md`
- **Changing database schema**: Update `storage/init_complete.sql`, add migration script

---

**Last Updated**: 2026-04-16  
**Version**: v3.2 (LlamaParse migration)  
**Maintainer**: Project Team
