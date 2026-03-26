# 🚀 LiteParse MCP 服務 - 快速開始指南

> 第一步：建立基於 MCP 的 LiteParse 工具服務 ✅ **已完成**
> 
> **所有依賴已包含喺 Docker 容器入面，無需用戶手動安裝！** 🎉

本指南帶你快速啟動同測試 LiteParse MCP 服務，令 Nanobot 可以調用佢去解析財報 PDF。

---

## 📋 系統架構

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   Nanobot   │ ───→ │  MCP Server      │ ───→ │  LiteParse CLI  │
│   (Agent)   │ HTTP │  (Node.js + HTTP) │ CLI  │  (PDF Parser)   │
└─────────────┘      └──────────────────┘      └──────────────────┘
                              │
                              ↓
                     ┌─────────────────┐
                     │ Data Cleaner    │
                     │ (Python)        │
                     └─────────────────┘
```

---

## 🎯 啟動方式

### 🐳 Docker 容器模式（唯一推薦）

**所有依賴已自動安裝喺 Docker 容器入面！** 無需要手動安裝任何嘢。

**步驟 1：一鍵啟動**

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot
docker-compose up -d
```

**步驟 2：檢查日誌**

```bash
docker-compose logs -f
```

你應該見到：
```
liteparse-mcp      | LiteParse MCP Server running on HTTP port 3000
nanobot-gateway    | Nanobot started successfully
```

**步驟 3：停止服務**

```bash
docker-compose down
```

---

### 💻 本地開發模式（可選，僅用於調試）

**⚠️ 注意：** 除非你需要調試源代碼，否則請使用 Docker 模式。

如果你真係需要本地開發，先至需要安裝依賴：

```bash
# 安裝 LiteParse CLI
npm install -g @llamaindex/liteparse

# 安裝 Python 依賴
pip install pymupdf pillow

# 安裝 Node.js 依賴
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\liteparse-mcp-server
npm install
```

**步驟 1：啟動 MCP Server**

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\liteparse-mcp-server
node index.js
```

**步驟 2：配置 Nanobot**

編輯 [`config/config.yaml`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/config/config.yaml)，將 MCP 配置改為 `stdio` 模式。

**步驟 3：啟動 Nanobot**

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot
nanobot start
```

---

## 🧪 測試流程

### 測試 1：直接調用 LiteParse CLI

```bash
# 測試 PDF 路徑
$PDF_PATH = "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\LightRAG\data\input\__enqueued__\SFC_annual_report_2023-24.pdf"

# 解析 PDF
lit parse $PDF_PATH --format json | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

### 測試 2：使用 Python 測試腳本

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot
py test_liteparse_quick.py --pages "10-12"
```

### 測試 3：端到端測試（推薦）

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot
py test_end_to_end.py
```

如果所有測試通過，你會見到：
```
✅ 所有測試通過！LiteParse MCP 服務已準備好供 Nanobot 使用。
```

---

## 💡 實際使用範例

### 場景 1：用戶問「幫我分析 SFC 年報嘅資產負債表」

**Nanobot 內部流程：**

1. Agent 識別用戶意圖：需要解析財報 PDF
2. 自動調用 MCP 工具：`parse_financial_table`
3. LiteParse 解析 PDF，返回 JSON
4. Data Cleaner 過濾噪音，提取財務表格
5. 轉換成 Markdown 格式
6. Agent 根據 Markdown 表格回答用戶

**MCP 工具調用範例：**

```json
{
  "tool": "parse_financial_table",
  "arguments": {
    "pdf_path": "C:/path/to/SFC_annual_report_2023-24.pdf",
    "pages": "10-15",
    "output_format": "context",
    "max_tables": 10
  }
}
```

**返回結果（簡化版）：**

```markdown
# 財務報表數據 (Financial Report Data)

共找到 3 個財務表格

## 表格 1: 資產負債表 (第 10 頁)
置信度：0.90

| 項目 | 2023 | 2022 |
|------|------|------|
| 總資產 | 5,000,000 | 4,500,000 |
| 總負債 | 2,000,000 | 1,800,000 |
| 股東權益 | 3,000,000 | 2,700,000 |

## 表格 2: 利潤表 (第 12 頁)
置信度：0.85

| 項目 | 2023 | 2022 |
|------|------|------|
| 收入 | 1,000,000 | 900,000 |
| 毛利 | 500,000 | 450,000 |
| 淨利 | 200,000 | 180,000 |
```

**Agent 回答：**

> 根據 SFC 年報第 10 頁嘅資產負債表，2023 年嘅財務狀況如下：
> 
> - **總資產**: 500 萬港元，按年增長 11.1%
> - **總負債**: 200 萬港元，按年增長 11.1%
> - **股東權益**: 300 萬港元，按年增長 11.1%
> 
> 從第 12 頁嘅利潤表見到，2023 年收入同淨利都穩定增長...

---

## 📊 數據清洗效果對比

| 階段 | 數據量 | 表格數量 | 適合 LLM？ |
|------|--------|----------|-----------|
| 原始 PDF | 50 頁 | - | ❌ 無法直接處理 |
| LiteParse 原始輸出 | 100KB JSON | 50 個（包括噪音） | ⚠️ 太多噪音 |
| Data Cleaner 處理後 | 5KB Markdown | 20 個（高置信度） | ✅ 完美 |

---

## 🛠️ 常見問題排解

### 問題 1：`lit: command not found`

**解決方案：**
```bash
npm install -g @llamaindex/liteparse
```

如果仍然失敗，檢查 npm 全局路徑：
```bash
npm config get prefix
```

將該路徑添加到系統 PATH 環境變量。

### 問題 2：MCP Server 無法啟動

**檢查日誌：**
```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\liteparse-mcp-server
node index.js 2>&1 | tee mcp.log
```

**常見原因：**
- Node.js 版本過低（需要 >= 18.0.0）
- 依賴未安裝（運行 `npm install`）
- 端口被佔用（HTTP 模式預設 3000）

### 問題 3：Data Cleaner 返回錯誤

**檢查 Python 依賴：**
```bash
pip install --upgrade pymupdf pillow
```

**測試 Data Cleaner：**
```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\liteparse-mcp-server
python liteparse_data_cleaner.py --help
```

### 問題 4：Docker 容器無法啟動

**檢查 Docker 狀態：**
```bash
docker ps
docker-compose ps
```

**查看錯誤日誌：**
```bash
docker-compose logs liteparse-mcp
docker-compose logs nanobot-gateway
```

**重新建置：**
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## 📁 關鍵文件位置

| 文件 | 路徑 | 說明 |
|------|------|------|
| MCP Server | [`liteparse-mcp-server/index.js`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/liteparse-mcp-server/index.js) | Node.js MCP 服務主程式 |
| Data Cleaner | [`liteparse-mcp-server/liteparse_data_cleaner.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/liteparse-mcp-server/liteparse_data_cleaner.py) | Python 數據清洗層 |
| Nanobot 工具 | [`nanobot/agent/tools/liteparse.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/nanobot/agent/tools/liteparse.py) | LiteParse 工具實現 |
| 配置文件 | [`config/config.yaml`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/config/config.yaml) | Nanobot + MCP 配置 |
| Docker Compose | [`docker-compose.yml`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/docker-compose.yml) | 容器化部署配置 |
| 測試腳本 | [`test_end_to_end.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/test_end_to_end.py) | 端到端測試 |

---

## 🎯 下一步（第二步：數據清洗與 Prompt 設計）

第一步完成後，你可以繼續：

1. **優化數據清洗邏輯**：根據實際財報調整關鍵詞同置信度閾值
2. **設計 System Prompt**：教導 LLM 如何嚴格根據 Markdown 表格回答
3. **測試真實場景**：用實際 SFC 年報測試端到端流程
4. **優化 Context Window**：調整 `max_tables` 同 `max_text_snippets`

---

## 📞 需要幫助？

如果喺啟動或者測試過程中遇到問題：

1. 檢查 [`test_end_to_end.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/test_end_to_end.py) 嘅測試結果
2. 查看 Docker 日誌：`docker-compose logs -f`
3. 參考完整文檔：[`IMPLEMENTATION_ZH.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/IMPLEMENTATION_ZH.md)

**第一步 ✅ 已完成：MCP LiteParse 工具服務已就緒！** 🎉
