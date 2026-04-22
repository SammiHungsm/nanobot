# Pipeline Architecture 文档

## 各 Stage 职责说明

本文档详细说明 Agentic Ingestion Pipeline 中各个 Stage 的职责和相互关系。

---

## Stage 流程概览

**🌟 v4.0 重要更新：Stage 1 先行**

在 v4.0 版本中，Stage 1 (LlamaParse) 最先執行，然後 Stage 0 (Vision) 分析 Page 1 的 artifacts。
這樣做的好處是：LlamaParse 解析後有完整的 Markdown + 圖片，Vision 提取公司信息更準確。

```
Stage 1: Parser (LlamaParse) 🌟 最先執行
Stage 0: Preprocessor (Vision 分析 Page 1)
Stage 0.5: Registrar (Hash + 注册)
Stage 2: Enrichment (RAGAnything 上下文分析)
Stage 3: Router (关键字掃描與頁面路由)
Stage 3.5: Context Builder (結構化上下文)
Stage 4: Agentic Extractor (Tool Calling 结构化提取)
Stage 4.5: KG Extractor (知識圖譜)
Stage 5: Vanna Training
Stage 6: Validator (数据验证)
Stage 7: Vector Indexer (RAG 文本切块 + Embedding)
Stage 8: Archiver (归档 + 清理)
Stage 9: Image Text Linker (圖文關聯) 🆕
```

---

## Stage 详细说明

### Stage 1：LlamaParse 解析器 🌟 最先執行

**核心職責**：PDF 解析與 Artifacts 提取

**實現位置**：`nanobot/ingestion/stages/stage1_parser.py`

**功能說明**：
- 🌟 **Stage 1 先行**：在 v4.0 中最先執行，為後續 Stage 提供完整的 artifacts
- 使用 LlamaParse Cloud API 解析 PDF
- 輸出：Markdown + JSON Artifacts（文本、表格、圖片）
- 創建 raw output 文件夾，保存解析結果

**輸入**：
- PDF 文件路徑

**輸出**：
- artifacts 列表（文本區塊、表格、圖片）
- raw_output_dir（解析結果目錄）

---

### Stage 0：Vision 分析 Page 1

**核心職責**：從 Page 1 提取公司基本信息

**實現位置**：`nanobot/ingestion/stages/stage0_preprocessor.py`

**功能說明**：
- 🌟 **基於 LlamaParse artifacts**：分析 Stage 1 輸出的 Page 1 artifacts
- 使用 Vision API 從圖片和 Markdown 提取公司資訊
- 提取：stock_code, year, name_en, name_zh
- 🌟 **v4.7 更新**：已移除 PyMuPDF 依賴
- 多圖片 Vision 合併邏輯

**輸入**：
- Stage 1 輸出的 artifacts 列表
- Stage 1 輸出的 images 列表
- raw_output_dir（圖片目錄）

**輸出**：
- 公司基本信息（stock_code, year, name_en, name_zh）

**重要提醒**：
- Stage 0 依賴 Stage 1 的輸出，不能獨立運行

---

### Stage 0.5：註冊器

**核心職責**：文件和公司註冊

**實現位置**：`nanobot/ingestion/stages/stage0_5_registrar.py`

**功能說明**：
- 計算文件 Hash（去重）
- 寫入 documents 表
- 寫入 companies 表
- 行業規則判斷（Rule A: 指數報告 / Rule B: 年報）

**輸入**：
- PDF 文件路徑
- Stage 0 輸出的公司信息

**輸出**：
- company_id
- document_id

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