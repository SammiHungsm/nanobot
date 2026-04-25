---
name: document-indexer
description: 處理一個或多個 [Doc: /path/to/file.pdf] 格式的請求。支援建立極速導航地圖、目錄跳轉、以及多文件對比分析。
metadata: {"nanobot":{"emoji":"📑"}}
---

# Document Indexer & Multi-Router

這是一個用於長篇財報的「導航地圖」系統。主 Agent 負責透過索引分析目錄並制定搜尋策略，隨後指派 Sub-agent 進入特定頁面進行數據深挖。

## When to use

當用戶訊息中包含一個或多個 `[Doc: ...]` 標籤，或需要：

- 獲取公司基本資訊（公司名、年份、股份代號）
- 在長文件中快速定位特定財務表格或章節
- 對比兩份或多份財報的數據（例如 YoY 增長或跨公司比較）

## 🔀 意圖路由：選擇正確的工具

**這是關鍵！根據問題類型選擇正確的工具：**

### 使用 `direct_sql` (SQL 查詢) 當：
- 問題涉及**具體財務指標**（營收、利潤、資產、負債、現金流等）
- 需要**計算**（增長率、比率、平均值、總和）
- 需要**排行**（前 10 大、最高、最低）
- 需要**跨年比較**或**趨勢分析**
- 問題可以用數字回答
- 持股量、公司關係等結構化數據

**示例：**
- "Show Tencent's revenue for 2020-2023"
- "Which company has the highest net margin?"
- "What is the average ROE for technology companies?"
- "Who holds more than 5% shares in this company?"

### 使用 `semantic_search` (語義搜索) 當：
- 問題涉及**主觀描述**或**政策解釋**
- 需要**業務描述**或**戰略分析**
- 需要**非結構化文本**（管理層討論、風險因素）
- 需要**未來展望**、**管理層評論**
- 問題無法用單一數字回答

**示例：**
- "What are Tencent's main business segments?"
- "Explain the company's risk management strategy"
- "What did management say about AI investment?"
- "Describe the impact of regulatory changes"
- "How does the chairman explain the revenue decline?"

### 使用文檔索引 (document-indexer) 當：
- 需要**精確頁碼**引用
- 需要**原始表格**或**圖表**
- 需要**驗證**Vanna 生成嘅 SQL 結果
- 用戶明確標註 `[Doc: ...]`

**示例：**
- "Show me the exact table on page 45"
- "Extract the full cash flow statement"
- "Find the auditor's report section"

---

## Workflow: The "Map & Strike" Pattern

### 1. 建立地圖 (Map Discovery)

若目標文件的索引資料夾 `workspace/indexes/<doc_name>/` 不存在，必須先執行：

```
python nanobot/skills/document_indexer/scripts/build_indexes.py "<pdf_path>"
```

*針對多個 [Doc:] 標籤，請依序為每一份文件執行此指令。*

### 2. 戰略分析 (Strategic Planning)

在正式回答前，主 Agent 必須讀取地圖檔案以鎖定目標頁碼：

- **背景核實**：`read_file` -> `metadata.md` (確保公司與年份 100% 準確)
- **目錄導航**：`read_file` -> `toc.md` (掃描所有章節名稱)
- **語義參考**：`read_file` -> `navigation_context.md` (前 5 頁摘要與結構)

### 3. 多文件對比 (Comparison Mode)

若涉及多份文件，請先分別找出各文件對應數據的 `Physical Page: X`，再集中指派 Sub-agent 提取。

## 範例指令 (Examples)

**搜尋目錄中的利潤表：**

```
python -c "from pathlib import Path; text = Path('workspace/indexes/<doc_name>/toc.md').read_text(encoding='utf-8'); print('\n'.join([l for l in text.splitlines() if '利潤表' in l.lower()]))"
```

**召喚 Sub-agent 執行精準提取：**
使用 `spawn` 工具並給予具體指令：

> "我是主 Agent。根據地圖分析，關於 [營收數據] 極大可能在該 PDF 的第 X 頁。請你作為提取員，使用 PyMuPDF 讀取第 X 頁並以 Markdown 回報表格細節。"
> 

## ⚠️ 執行準則

- **標籤驅動**：嚴格使用用戶標註的 `[Doc: ...]` 路徑。
- **身份優先**：回覆任何數據前，必須先報出 `metadata.md` 內的公司全稱與 Stock Code。
- **證據綁定**：所有提取的數據必須附帶 `(Data from Physical Page: X)`。
- **分層思考**：主 Agent 負責「看地圖」和「猜頁碼」；Sub-agent 負責「讀原始頁面」和「拿數」。
- **禁止猜測**：若目錄不明確，請先讀取 `navigation_context.md` 尋找線索或詢問用戶。
- **工具選擇**：具體數字問題優先使用 `direct_sql`，主觀描述先用語義搜索 `semantic_search`。
- **雙軌制**：數字型問題 → `direct_sql` | 策略型問題 → `semantic_search`
- **SQL 安全**：`direct_sql` 執行查詢時使用參數化查詢防止 SQL 注入。
