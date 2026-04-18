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

**功能說明**：
- 根據預先定義或動態加載的關鍵字地圖（例如搜尋 "revenue breakdown" 或 "key_personnel" 等字眼）去掃描所有的 artifacts（包含文本區塊和表格）
- 最終目的是返回一個「候選頁面列表」（例如：知道收入分佈數據可能在第 12 頁和 45 頁）
- 告訴後續的提取階段應該去哪些頁面找資料，從而避免把整本 PDF 丟給 LLM 造成浪費

**輸入**：
- LlamaParse 解析后的 artifacts（文本區塊、表格）

**輸出**：
- 候選頁面列表（keyword_pages）
- 關鍵字匹配結果

**重要提醒**：
- Stage 3 **不是**負責做 RAGAnything 加上下文或文本切塊 (Chunking) 的階段
- 它像是一個快速搜尋引擎，幫忙定位包含特定關鍵字的頁碼

---

### Stage 2：RAGAnything (圖片 + 文本上下文分析)

**核心職責**：多模態富文本擴充 (v3.4 RAGAnything 上下文)

**實現位置**：`nanobot/ingestion/stages/stage2_enrichment.py`

**功能說明**：
- 執行「像 RAGAnything 那樣抽圖片並加上下文」的功能
- 準備分析圖片時，會先提取同一頁的文字作為 Context
- 把圖片連同這些上下文一起餵給 Vision LLM
- 要求模型分析「這張圖表與上下文的關聯是什麼？」

**輸入**：
- LlamaParse 解析后的图片列表
- 同页文本内容（作为 Context）

**輸出**：
- Vision 分析结果
- 图片与文本的关联分析

**設計理念**：
- Stage 2 被明確設計為執行「多模態富文本擴充」
- 理解圖片的上下文含義，而不是單純 OCR

---

### Stage 7：RAG 文本切塊與向量入庫

**核心職責**：文本切塊 (Semantic Chunking) + Embedding + 向量入庫

**實現位置**：`nanobot/ingestion/stages/stage7_vector_indexer.py`

**功能說明**：
- 真正的「多模態 RAG 準備」
- 將前面的文本以及圖片的分析結果（Vision Analysis）一起切塊
- 生成 Embedding 向量
- 寫入向量資料庫中

**輸入**：
- 所有 document_pages 的文本内容
- Vision Analysis 结果
- 提取的结构化数据

**輸出**：
- 文本切块 (Chunks)
- Embedding 向量
- 向量数据库记录

**重要提醒**：
- Stage 7 才是最後為 RAG 系統建立向量分塊的階段
- 不在 Stage 3 做切块

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