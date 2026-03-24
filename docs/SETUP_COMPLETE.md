# 🚀 WebAPI Channel 設置完成！

> 而家 WebUI 可以真正調用 Nanobot Agent 嘅能力啦！✅

---

## ✅ 已完成嘅工作

### 1. **WebAPI Channel** ([`channels/webapi.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/nanobot/channels/webapi.py))
- ✅ HTTP REST API (`/api/chat`, `/api/health`)
- ✅ 連接 Nanobot Message Bus
- ✅ 等待 Agent 回應並返回給前端
- ✅ CORS 配置支持網頁訪問

### 2. **配置更新**
- [`config.json`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/config/config.json) - 啟用 WebAPI Channel（端口 8081）
- [`docker-compose.yml`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/docker-compose.yml) - 暴露 8081 端口
- [`chat_logic.py`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/chat_logic.py) - 調用真實 WebAPI

### 3. **統一 PDF 目錄**
所有服務都使用同一個 PDF 目錄：
```
C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\LightRAG\data\input\__enqueued__
```

---

## 🎯 啟動步驟

### 步驟 1：重啟所有服務

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot
docker-compose down
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
nanobot-gateway     Up                  18790/tcp, 0.0.0.0:8081->8081/tcp
nanobot-webui       Up                  0.0.0.0:3000->8080/tcp
```

### 步驟 3：測試 WebAPI Channel

```bash
# 測試健康檢查
curl http://localhost:8081/api/health

# 測試對話 API
curl -X POST http://localhost:8081/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "username": "test"}'
```

### 步驟 4：訪問 Web UI

喺瀏覽器打開：**http://localhost:3000**

---

## 📊 系統架構

```
┌─────────────────┐
│   Web Browser   │
│  (localhost:3000)│
└────────┬────────┘
         │ HTTP
         ↓
┌─────────────────┐      ┌──────────────────┐
│  Nanobot WebUI  │ ───→ │ LiteParse MCP    │
│  (FastAPI)      │ HTTP │ Server           │
│  Port 8080      │      │ Port 3000        │
└────────┬────────┘      └──────────────────┘
         │ HTTP (WebAPI Channel)
         ↓
┌─────────────────┐
│ Nanobot Gateway │
│ Port 8081       │
└─────────────────┘
```

---

## 🔧 訪問地址總結

| 服務 | 地址 | 用途 |
|------|------|------|
| **Web UI** | http://localhost:3000 | 網頁聊天介面 |
| **WebAPI** | http://localhost:8081/api/chat | REST API |
| **WebUI Health** | http://localhost:3000/health | WebUI 健康檢查 |
| **WebAPI Health** | http://localhost:8081/api/health | WebAPI 健康檢查 |
| **Nanobot Gateway** | http://localhost:18790 | Gateway 管理介面 |

---

## 🧪 測試對話

### 使用 Web UI 測試

1. 訪問 http://localhost:3000
2. 登入（任意用戶名）
3. 輸入："Hello" 或者 "Help"
4. 應該收到 Nanobot Agent 嘅真實回應！

### 使用 curl 測試

```bash
# 測試基本對話
curl -X POST http://localhost:8081/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, I need help with financial analysis",
    "username": "test-user",
    "chat_id": "test-chat"
  }'

# 測試文件分析
curl -X POST http://localhost:8081/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "[Doc: /data/pdfs/SFC_annual_report_2023-24.pdf] What is the total revenue?",
    "username": "analyst"
  }'
```

---

## 🛠️ 常見問題排解

### Q1: WebAPI Channel 無啟動？

**檢查日誌：**
```bash
docker-compose logs nanobot-gateway | grep -i webapi
```

應該見到：
```
WebAPI Channel started on http://0.0.0.0:8081
```

### Q2: 504 Gateway Timeout？

Agent 處理超時（預設 60 秒），可以：
1. 增加超時時間（修改 `webapi.py` 嘅 `timeout=60.0`）
2. 檢查 Agent 是否正常運行

### Q3: CORS 錯誤？

如果前端訪問 API 有 CORS 錯誤，修改 `webapi.py`：
```python
allow_origins=["http://localhost:3000"],  # 指定域名
```

### Q4: PDF 文件無法訪問？

確保所有服務都掛載咗同一個 PDF 目錄：
```bash
docker-compose exec nanobot-gateway ls /data/pdfs
docker-compose exec nanobot-webui ls /data/pdfs
docker-compose exec liteparse-mcp ls /data/pdfs
```

---

## 🎉 完成！

而家你嘅系統已經完全打通：

1. ✅ Web UI 前端可以調用 Nanobot Agent
2. ✅ Agent 可以使用 LiteParse MCP 工具
3. ✅ 所有服務共享同一個 PDF 目錄
4. ✅ 支持真實嘅財務報告分析

**試吓訪問 http://localhost:3000 同個 Agent 傾偈啦！** 🚀
