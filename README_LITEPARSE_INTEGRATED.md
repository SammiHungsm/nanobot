# 🚀 LiteParse + Nanobot 財報分析 Chatbot

> 全部代碼已整合到呢個 `nanobot` 目錄入面，包括 MCP Server、數據清洗層、Debugger 同 Docker 配置。

---

## 📦 目錄結構

```
nanobot/
├── nanobot/                      # Nanobot 主程式
│   ├── agent/
│   │   └── tools/
│   │       └── liteparse.py      # LiteParse 工具 (Python)
│   └── tests/
│       └── tools/
│           └── test_liteparse.py # 測試套件
│
├── liteparse-mcp-server/         # MCP Server (已整合數據清洗)
│   ├── package.json
│   ├── index.js                  # MCP Server 主程式
│   ├── liteparse_data_cleaner.py # 🆕 Python 數據清洗層
│   ├── Dockerfile
│   └── README.md
│
├── liteparse-debugger/           # 調試工具
│   └── visualize.py              # 可視化 bounding boxes
│
├── config/
│   └── config-liteparse-example.yaml  # MCP 配置範例
│
├── Dockerfile                    # Nanobot Docker 鏡像
└── README_LITEPARSE.md           # 完整文檔 (英文)
```

---

## ✨ 核心功能

### 1. **MCP LiteParse 工具服務** (`liteparse-mcp-server/`)

透過 MCP 協議提供三個工具：

- `parse_financial_table`: 解析財報 PDF，支持三種輸出模式
- `get_pdf_screenshot`: 生成頁面截圖
- `query_financial_data`: 提取特定財務指標

**數據清洗層已整合** → 自動過濾噪音、分類表格、轉 Markdown

### 2. **Python 數據清洗層** (`liteparse_data_cleaner.py`)

- 移除頁首頁尾、版權、URL 等噪音
- 自動識別資產負債表/利潤表/現金流量表
- 置信度評分 (0.3-0.9)
- Markdown 格式化
- 優先級排序 (財務報表 > 附註 > 其他)

### 3. **可視化調試器** (`liteparse-debugger/visualize.py`)

- 渲染 bounding boxes 響 PDF 頁面
- 顏色區分元素類型（表格=綠色，文字=紅色...）
- 支持指定頁面範圍

---

## 🚀 快速開始

### 步驟 1: 安裝依賴

```bash
# 安裝 LiteParse CLI
npm install -g @llamaindex/liteparse

# 安裝 Python 依賴（數據清洗層）
pip install pymupdf pillow
```

### 步驟 2: 配置 Nanobot

```bash
cd nanobot

# 複製配置範例
cp config/config-liteparse-example.yaml config/config.yaml

# 編輯 config.yaml，設置你嘅 API Key
# model.api_key: ${OPENAI_API_KEY}
```

### 步驟 3: 測試解析

```bash
# 運行快速測試
python nanobot/agent/tools/liteparse.py

# 或者使用測試腳本
cd ..
python test_liteparse_quick.py --pages "10-12"
```

### 步驟 4: Docker 部署（可選）

```bash
# 設置環境變量
export OPENAI_API_KEY="sk-..."

# 一鍵啟動
docker-compose up -d

# 查看日誌
docker-compose logs -f
```

---

## 💡 使用範例

### 範例 1: 解析財報

```python
from nanobot.agent.tools.liteparse import LiteParseTool

tool = LiteParseTool()

# 解析資產負債表頁面，使用 LLM-ready 格式
result = await tool.execute(
    pdf_path="C:/path/to/SFC_annual_report.pdf",
    pages="10-15",
    output_format="context"  # 自動數據清洗 + Markdown 格式化
)

print(result)
```

### 範例 2: 可視化調試

```bash
# 渲染 bounding boxes
python liteparse-debugger/visualize.py \
  --pdf "C:/path/to/report.pdf" \
  --output ./debug_output \
  --pages "10-12" \
  --show-text
```

### 範例 3: MCP 對話

```
用戶：幫我分析 SFC 年報嘅資產負債表

Agent → 使用 parse_financial_table (output_format="context")
      → 接收清洗後嘅 Markdown 表格
      → 分析並回應：「根據第 10 頁嘅資產負債表，2023 年總資產為...」
```

---

## 📊 數據清洗效果

**原始 LiteParse 輸出:**
- 500 個元素（包括頁碼、URL、版權）
- 50 個表格（只有 20 個係真正財務表格）
- 100MB JSON

**清洗後 (`context` 模式):**
- 20 個高置信度財務表格
- 50 個關鍵數據片段
- 50KB Markdown → 完美適合 LLM Context Window

---

## 🛠️ 配置選項

### MCP Server 配置

```yaml
mcp:
  servers:
    liteparse:
      type: stdio  # 開發模式
      command: node
      args:
        - /path/to/nanobot/liteparse-mcp-server/index.js
      cwd: /path/to/nanobot/liteparse-mcp-server
      
      # 或 Docker 模式
      # type: http
      # url: http://liteparse-mcp:3000
```

### 數據清洗選項

```python
from liteparse_data_cleaner import FinancialDataCleaner

cleaner = FinancialDataCleaner(
    min_table_rows=3,     # 最少 3 行
    min_confidence=0.5,   # 最低置信度
)

# 自定義關鍵詞
cleaner.TABLE_TYPE_KEYWORDS['esg_report'] = ['ESG', 'environmental']
```

---

## 📁 完整文件清單

| 文件 | 說明 |
|------|------|
| `nanobot/agent/tools/liteparse.py` | LiteParse 工具 (15.7KB) |
| `nanobot/tests/tools/test_liteparse.py` | 測試套件 (10.8KB) |
| `liteparse-mcp-server/index.js` | MCP Server (10.7KB) |
| `liteparse-mcp-server/liteparse_data_cleaner.py` | 數據清洗層 (15.5KB) |
| `liteparse-mcp-server/Dockerfile` | Docker 配置 |
| `liteparse-debugger/visualize.py` | 可視化工具 (8.8KB) |
| `config/config-liteparse-example.yaml` | 配置範例 |
| `Dockerfile` | Nanobot 容器 |
| `../docker-compose.yml` | Docker Compose |
| `../IMPLEMENTATION_ZH.md` | 中文完整指南 (13KB) |

---

## 🧪 測試

```bash
cd nanobot

# 運行完整測試套件
pytest tests/tools/test_liteparse.py -v

# 運行單個測試
pytest tests/tools/test_liteparse.py::TestLiteParseTool::test_parse_sample_pdf -v
```

---

## 📖 文檔

- **中文完整指南**: [`../IMPLEMENTATION_ZH.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/IMPLEMENTATION_ZH.md)
- **英文技術文檔**: [`README_LITEPARSE.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/README_LITEPARSE.md)
- **實現總結**: [`../IMPLEMENTATION_SUMMARY.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/IMPLEMENTATION_SUMMARY.md)

---

## 🎯 下一步

1. ✅ 安裝 LiteParse CLI: `npm install -g @llamaindex/liteparse`
2. ✅ 配置 Nanobot: `cp config/config-liteparse-example.yaml config/config.yaml`
3. ✅ 測試解析：`python test_liteparse_quick.py`
4. ✅ 啟動 Nanobot: `nanobot start`
5. ✅ Docker 部署：`docker-compose up -d`

---

**全部代碼已整合到 `nanobot` 目錄，一鍵部署，無縫協作！** 🎉
