# Pipeline Architecture 文档

## 各 Stage 职责说明

本文档详细说明 Agentic Ingestion Pipeline 中各个 Stage 的职责和相互关系。

---

## Stage 流程概览

```
Stage 0: Preprocessor (封面 Vision) - 独立运行
Stage 0.5: Registrar (Hash + 注册)
Stage 1: Parser (LlamaParse)
Stage 2: Enrichment (RAGAnything 上下文分析)
Stage 3: Router (关键字掃描與頁面路由)
Stage 4: Agentic Extractor (Tool Calling 结构化提取)
Stage 5: Vanna Training
Stage 6: Validator (数据验证)
Stage 7: Vector Indexer (RAG 文本切块 + Embedding)
Stage 8: Archiver (归档 + 清理)
```

---

## Stage 详细说明

### Stage 3：关键字掃描與頁面路由 (過濾器)

**核心職責**：關鍵字掃描與目標頁面路由

**實現位置**：`nanobot/ingestion/stages/stage3_router.py`

**配置文件**：`nanobot/ingestion/config/financial_terms_mapping.json`

**功能說明**：
- 🌟 **100% 配置驱动 (Configuration-Driven)**：关键字定义完全依赖外部 JSON
- 🌟 Python 程式码纯粹负责逻辑运算，不再夹带业务资料（财报术语）
- 根據預先定義或動態加載的關鍵字地圖（例如搜尋 "revenue breakdown" 或 "key_personnel" 等字眼）去掃描所有的 artifacts（包含文本區塊和表格）
- 最終目的是返回一個「候選頁面列表」（例如：知道收入分佈數據可能在第 12 頁和 45 頁）
- 告訴後續的提取階段應該去哪些頁面找資料，從而避免把整本 PDF 丟給 LLM 造成浪費

**核心方法**：
1. `_load_keywords_from_json()`: 🌟 强制从外部 JSON 载入关键字对应表
2. `get_keyword_map()`: 🌟 获取当前的关键字对应表
3. `add_keywords()`: 🌟 动态添加关键字（Agentic 学习）

**輸入**：
- LlamaParse 解析后的 artifacts（文本區塊、表格）
- `financial_terms_mapping.json` 配置文件

**輸出**：
- 候選頁面列表（keyword_pages）
- 關鍵字匹配結果

**設計理念**：
- **极致的 Clean Code**：Python 程式码变得非常干净，纯粹负责「逻辑运算（扫描与路由）」，不再夹带「业务资料（财报术语）」
- **无缝接轨 Agentic 学习**：当 Stage 4 的 Agent 发现新字眼并写入 JSON 时，Stage 3 在下一次载入时就会立刻生效，完全不需要动到 Python 程式码
- **多语言/领域切换**：未来如果要做「医疗报告」分析，只需要抽换成 `medical_terms_mapping.json`，Python 程式码一行都不用改

**重要提醒**：
- Stage 3 **不是**負責做 RAGAnything 加上下文或文本切塊 (Chunking) 的階段
- 它像是一個快速搜尋引擎，幫忙定位包含特定關鍵字的頁碼
- 🌟 如果找不到 `financial_terms_mapping.json`，Stage 3 会给出明确警告，而不是退回 hardcode

---

### Stage 2：RAGAnything (圖片 + 文本上下文分析)

**核心職責**：多模態富文本擴充 (v3.5 RAG-Anything 精準上下文與防禦性修復)

**實現位置**：`nanobot/ingestion/stages/stage2_enrichment.py`

**功能說明**：
- 🌟 **防禦性檢查**：攔截 LlamaParse 失敗的 Markdown 表格，動用 PyMuPDF 截圖重解
- 🌟 **層級上下文對齊 (Hierarchical Context Alignment)**：使用滑動視窗 (Sliding Window) 捕捉精準的結構化上下文
- 不再粗暴取整页文字（噪声太多，结构全无），而是寻找：
  - **closest_heading**: 最接近的标题
  - **caption**: 图表标签/图说 (如 "Figure 1:", "Table 2:")
  - **previous_text**: 图表前的引言
  - **next_text**: 图表后的解释分析
- 把图片连同这些精准上下文一起喂给 Vision LLM
- 输出完美 `markdown_representation`（直接进入向量数据库）

**核心方法**：
1. `_is_messy_table()`: 防禦性檢查（判斷表格是否解析失敗）
2. `_get_precise_context()`: 精准上下文提取（滑动窗口）
3. `_analyze_image_with_precise_context()`: 高阶 Vision 分析（结合结构化上下文）

**輸入**：
- LlamaParse 解析后的图片列表
- artifacts 列表（用于精准上下文提取）
- PDF 文件（用于防御性截图修复）

**輸出**：
- Vision 分析结果（包含 `markdown_representation`）
- 图片与文本的关联分析
- `structural_context`（存入 DB，Stage 7 切块时非常有用）
- 修复后的表格内容（如果原始 Markdown 表格解析失败）

**設計理念**：
- **防禦性容錯**：不會再被 LlamaParse 失敗的 Table 綁架，自動退回截圖模式
- **消除幻覺**：Vision LLM 看图时能核對上下文中的數據
- **完美繼承 RAGAnything 的精神**：Decoupling Parsing and Reasoning
- **优化 Database Raw Data**：将 `structural_context` 和完美的 `markdown_representation` 存入 PostgreSQL，Stage 7 切块时质量核弹级提升

---

### Stage 7：RAG 文本切塊與向量入庫

**核心職責**：文本切塊 (Semantic Chunking) + Embedding + 向量入庫

**實現位置**：`nanobot/ingestion/stages/stage7_vector_indexer.py`

**功能說明**：
- 真正的「多模態 RAG 準備」
- 🌟 使用 Stage 2 提煉的 RAG-Anything 精準上下文進行 Embedding
- 將前面的文本以及圖片的分析結果（Vision Analysis）一起切塊
- 生成 Embedding 向量
- 寫入向量資料庫中

**核心方法**：
1. `_semantic_chunking()`: 语义切块（按段落 + 句子边界）
2. `_generate_embedding()`: 本地 Embedding 生成（sentence-transformers）
3. `index_vision_artifacts()`: 🌟 Vision 索引（使用精准上下文）

**Vision Embedding 組合格式（RAG-Anything 高質量文字塊）**：
```
[圖表標題]: 2023年各區域收入分佈
[數據類型]: chart
[所屬章節]: ## Revenue Breakdown
[圖表標籤]: Figure 1: Revenue by Geography
[關聯前文]: The company's revenue...
[核心數據與描述]:
- 香港：45%
- 歐洲：30%
[關鍵實體]: 香港, 歐洲, 收入
```

**輸入**：
- 所有 document_pages 的文本内容
- Vision Analysis 结果
- structural_context（来自 Stage 2）
- 提取的结构化数据

**輸出**：
- 文本切块 (Chunks)
- Embedding 向量
- 向量数据库记录

**重要提醒**：
- Stage 7 才是最後為 RAG 系統建立向量分塊的階段
- 不在 Stage 3 做切块
- 🌟 Vision Embedding 使用 Stage 2 提煉的精准上下文，RAG 搜尋命中率將達到極致

---

## 职责分离总结

| Stage | 职责 | 不要做的事 |
|-------|------|-----------|
| Stage 2 | 圖片 + 文本上下文分析 (RAGAnything) | 不做切块、不做路由 |
| Stage 3 | 關鍵字掃描與頁面路由 (過濾器) | **不做** RAGAnything 上下文、**不做** 文本切塊 |
| Stage 7 | RAG 文本切塊 + Embedding | 不做关键字扫描、不做 Vision 分析 |

---

## 常见误解澄清

### ❌ 误解：Stage 3 负责做 RAGAnything 加上下文

**正确答案**：Stage 3 只是关键字扫描和页面路由，像是一个快速搜索引擎帮忙定位包含特定关键字的页码。

### ❌ 误解：Stage 3 负责做文本切块 (Chunking)

**正确答案**：文本切块在 Stage 7 执行，Stage 7 负责真正的「多模态 RAG 准备」。

### ❌ 误解：图片分析是独立阶段

**正确答案**：图片分析在 Stage 2 执行，作为「多模态富文本扩充」的一部分，会连同同一页的文字作为 Context 一起喂给 Vision LLM。

---

## 数据流向

```
PDF 文件
    ↓
Stage 1 (LlamaParse) → artifacts + images
    ↓
Stage 2 (Enrichment) → Vision Analysis (圖片 + 上下文)
    ↓
Stage 3 (Router) → keyword_pages (候選頁面列表)
    ↓
Stage 4 (Agentic) → 结构化数据提取
    ↓
Stage 7 (Vector Indexer) → Chunks + Embeddings
    ↓
向量数据库 (RAG 系统)
```

---

## 更新日志

- **2026-04-18**: 初始文档创建，澄清 Stage 2/3/7 的职责分离