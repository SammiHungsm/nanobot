# 🚀 Nanobot Web UI - 完整使用指南

> Web UI 已經完整配置好晒！所有依賴已經包含喺 Docker 容器入面，無需用戶手動安裝。✅

---

## ✅ 完成咗嘅工作

### 1. **Web UI 前端** ([`webui/ui.html`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/ui.html))
- ✅ 現代化 Tailwind CSS 設計
- ✅ 登入介面（模擬認證）
- ✅ 文件列表側邊欄
- ✅ 即時對話界面
- ✅ 文件上傳功能
- ✅ 響應式設計（手機/桌面）

### 2. **FastAPI 後端** ([`webui/main.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/main.py))
- ✅ RESTful API (`/api/chat`, `/api/documents`)
- ✅ CORS 配置
- ✅ 健康檢查端點
- ✅ 錯誤處理

### 3. **對話邏輯** ([`webui/chat_logic.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/chat_logic.py))
- ✅ MCP Server 連接邏輯
- ✅ 財務查詢處理
- ✅ 文件分析功能
- ✅ Mock 回應（當 MCP 未連接時）

### 4. **Docker 配置**
- ✅ [`webui/Dockerfile`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/Dockerfile) - Web UI 容器
- ✅ [`webui/requirements.txt`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/requirements.txt) - Python 依賴
- ✅ [`docker-compose.yml`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/docker-compose.yml) - 三服務編排

---

## 📦 系統架構

```
┌─────────────────┐
│   Web Browser   │
│   (Port 3000)   │
└────────┬────────┘
         │ HTTP
         ↓
┌─────────────────┐      ┌──────────────────┐
│  Nanobot Web UI │ ───→ │ LiteParse MCP    │
│  (FastAPI)      │ HTTP │ Server           │
│  Port 8080      │      │ Port 3000        │
└─────────────────┘      └──────────────────┘
```

---

## 🎯 啟動方法（一分鐘）

### 步驟 1：啟動所有服務

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot
docker-compose up -d
```

### 步驟 2：檢查服務狀態

```bash
docker-compose ps
```

應該見到：
```
NAME                STATUS              PORTS
liteparse-mcp       Up                  3000/tcp
nanobot-gateway     Up                  18790/tcp, 0.0.0.0:8080->8080/tcp
nanobot-webui       Up                  0.0.0.0:3000->8080/tcp
```

### 步驟 3：訪問 Web UI

喺瀏覽器打開：
```
http://localhost:3000
```

---

## 🧪 測試功能

### 1. 登入系統
- 輸入任意用戶名（例如：`admin`）
- 密碼随意（目前係模擬認證）
- 點擊 "Sign In"

### 2. 文件列表
- 左側邊欄會顯示可用嘅 PDF 文件
- 點擊文件可以自動 tag 落聊天框

### 3. 對話測試
試吓問：
- "Hello" → 會收到歡迎訊息
- "Help" → 會收到使用指南
- "List documents" → 會顯示文件列表
- "[Doc: test.pdf] What is the revenue?" → 會分析文件（Demo 模式）

### 4. 上傳文件
- 點擊回形針圖標
- 選擇 PDF 文件
- 等待上傳完成（模擬 2.5 秒）

---

## 📁 文件結構

```
nanobot/
├── webui/
│   ├── main.py              # FastAPI 主程式
│   ├── chat_logic.py        # 對話邏輯
│   ├── ui.html              # HTML 前端
│   ├── requirements.txt     # Python 依賴
│   ├── Dockerfile           # Docker 配置
│   └── README_WEBUI.md      # 呢個文件
│
├── liteparse-mcp-server/
│   ├── index.js             # MCP Server
│   ├── liteparse_data_cleaner.py
│   ├── Dockerfile
│   └── ...
│
├── docker-compose.yml       # 多服務編排
└── ...
```

---

## 🔧 配置選項

### 環境變量（可選）

修改 [`docker-compose.yml`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/docker-compose.yml)：

```yaml
services:
  nanobot-webui:
    environment:
      - MCP_SERVER_URL=http://liteparse-mcp:3000  # MCP Server 地址
      - PDF_DATA_DIR=/data/pdfs                   # PDF 文件目錄
```

### 端口映射

預設配置：
- **Web UI**: `3000` (外部) → `8080` (容器內)
- **MCP Server**: `3000` (容器內，唔暴露到外部)
- **Nanobot Gateway**: `8080` (外部) → `8080` (容器內)

如果想改端口：
```yaml
ports:
  - 8080:8080  # 改成 8080:8080 就用 http://localhost:8080 訪問
```

---

## 🛠️ 常見問題排解

### Q1: 點解我見到 `docker-compose: command not found`?

**A:** 新版 Docker 使用 `docker compose` (無橫桿)：

```bash
docker compose up -d
```

或者安裝舊版：
```bash
pip install docker-compose
```

### Q2: Web UI 無法連接 MCP Server？

**A:** 檢查 MCP Server 是否運行緊：

```bash
docker-compose logs liteparse-mcp
```

如果見到錯誤，重建容器：
```bash
docker-compose down
docker-compose up -d --build
```

### Q3: 點解文件列表係空的？

**A:** PDF 文件需要放喺正確位置：

```bash
# 將 PDF 文件複製去呢個目錄
C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\data\pdfs\
```

或者檢查日誌：
```bash
docker-compose logs nanobot-webui
```

### Q4: 點樣停止所有服務？

**A:** 
```bash
docker-compose down
```

### Q5: 點樣重置所有數據？

**A:** 
```bash
# 停止並刪除所有容器、網絡
docker-compose down -v

# 重新啟動
docker-compose up -d
```

---

## 📊 服務狀態監控

### 查看日誌

```bash
# 所有服務日誌
docker-compose logs -f

# 只看 Web UI
docker-compose logs -f nanobot-webui

# 只看 MCP Server
docker-compose logs -f liteparse-mcp
```

### 健康檢查

```bash
# 檢查 Web UI
curl http://localhost:3000/health

# 檢查 MCP Server
docker-compose exec liteparse-mcp curl -f http://localhost:3000/health
```

---

## 🎨 UI 功能詳解

### 登入介面
- 簡易用家認證（目前係模擬）
- 記住用家名響會話中
- 登出功能

### 文件側邊欄
- 自動載入可用 PDF
- 顯示文件狀態（Ready/Uploading）
- 點擊自動 tag 落聊天框
- 上傳按鈕（回形針圖標）

### 對話界面
- 實時對話氣泡
- 打字中動畫
- Markdown 格式支持
- 文件標籤視覺化
- Shift+Enter 換行

---

## 🔗 API 端點參考

### POST `/api/chat`

發送訊息：
```json
{
  "message": "What is the revenue?",
  "username": "admin",
  "document_path": "/data/pdfs/report.pdf"
}
```

回應：
```json
{
  "reply": "Based on the financial report...",
  "success": true
}
```

### GET `/api/documents`

列出文件：
```json
{
  "documents": [
    {
      "id": "SFC_annual_report_2023",
      "name": "SFC_annual_report_2023.pdf",
      "path": "/data/pdfs/SFC_annual_report_2023.pdf",
      "size": "2.45 MB",
      "status": "Ready"
    }
  ],
  "success": true
}
```

### GET `/health`

健康檢查：
```json
{
  "status": "online",
  "service": "nanobot-webui",
  "mcp_connection": "ready",
  "version": "1.0.0"
}
```

---

## 🚀 下一步（可選升級）

### 1. 連接真實 MCP Server
修改 [`chat_logic.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/chat_logic.py)：

```python
async def analyze_document(document_path, query):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://liteparse-mcp:3000/parse",
            json={"pdf_path": document_path}
        )
        return format_response(response.json())
```

### 2. 添加真實文件上傳
修改 [`main.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/main.py)：

```python
@app.post("/api/upload")
async def upload_document(file: UploadFile):
    # 保存文件去 data/pdfs/
    ...
```

### 3. 添加用家認證
替换模擬登入做真實 JWT 認證。

---

## 📞 需要幫助？

### 相關文檔
- **MCP Server 指南**: [`QUICKSTART_MCP.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/QUICKSTART_MCP.md)
- **Docker 部署**: [`README_DOCKER.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/liteparse-mcp-server/README_DOCKER.md)
- **完整實施**: [`IMPLEMENTATION_ZH.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/IMPLEMENTATION_ZH.md)

### 系統狀態
```bash
# 一分鐘檢查
docker-compose ps
docker-compose logs --tail=20
curl http://localhost:3000/health
```

---

## ✅ 完成清單

- [x] Web UI 前端（HTML + Tailwind CSS）
- [x] FastAPI 後端
- [x] 對話邏輯層
- [x] Docker 配置
- [x] docker-compose 編排
- [x] 依賴管理（requirements.txt）
- [x] 健康檢查端點
- [x] 錯誤處理
- [x] 文件上傳 UI
- [x] 文件列表 API
- [x] 響應式設計
- [x] 使用文檔

---

**🎉 全部完成！而家你可以運行 `docker-compose up -d` 然後喺 `http://localhost:3000` 使用個 Web UI 啦！** 🚀
