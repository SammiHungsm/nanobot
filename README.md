# 🚀 財報分析 Chatbot - LiteParse + Nanobot

> **第一步 ✅ 已完成：所有依賴已包含喺 Docker 容器入面，無需用戶手動安裝！**

一個基於 MCP 協議嘅高準確度財報分析 Chatbot，結合 Nanobot Agent 同 LiteParse PDF 解析工具。

---

## 🎯 一分鐘快速開始

### Windows 用戶

**方法 1: 雙擊啟動**
```
雙擊 start.bat
```

**方法 2: PowerShell**
```powershell
.\start.ps1
```

**方法 3: Docker Compose**
```bash
docker-compose up -d
```

### 訪問服務

- **Web UI:** http://localhost:8080
- **API:** http://localhost:18790

### 停止服務

```bash
docker-compose down
```

**就係咁簡單！** 🎉

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

## 🐳 Docker 容器包含咩？

### `liteparse-mcp` 容器

- Node.js 20.x
- LiteParse CLI (PDF 解析)
- Python 3.11
- PyMuPDF + Pillow (數據清洗)
- MCP SDK

### `nanobot-gateway` 容器

- Python 3.11
- Nanobot Agent 框架
- MCP Client

**所有依賴已自動安裝，無需用戶手動配置！**

---

## 💡 使用範例

### 場景：分析 SFC 年報

1. **上傳 PDF**
   將 PDF 放入 `data/pdfs/` 目錄

2. **對話**
   喺 Nanobot Web UI 輸入：
   ```
   幫我分析 SFC 年報嘅資產負債表
   ```

3. **內部流程**
   - Nanobot 自動調用 MCP 工具 `parse_financial_table`
   - LiteParse 解析 PDF
   - Data Cleaner 過濾噪音、轉 Markdown
   - Agent 根據表格數據回答

4. **結果**
   Agent 返回結構化分析結果

---

## 📁 目錄結構

```
nanobot/
├── start.bat              # Windows 一鍵啟動
├── start.ps1              # PowerShell 一鍵啟動
├── docker-compose.yml     # Docker 配置
├── config/                # 配置文件
├── data/pdfs/             # PDF 文件目錄
├── liteparse-mcp-server/  # MCP 服務
│   ├── index.js           # MCP Server
│   ├── liteparse_data_cleaner.py  # 數據清洗
│   └── Dockerfile
├── nanobot/               # Nanobot 主程式
│   └── agent/tools/liteparse.py   # LiteParse 工具
└── tests/                 # 測試套件
```

---

## 📚 文檔

| 文檔 | 說明 |
|------|------|
| [`FIRST_STEP_COMPLETE.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/FIRST_STEP_COMPLETE.md) | **第一步完成報告** |
| [`QUICKSTART_MCP.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/QUICKSTART_MCP.md) | 快速開始指南 |
| [`liteparse-mcp-server/README_DOCKER.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/liteparse-mcp-server/README_DOCKER.md) | Docker 部署指南 |
| [`README_LITEPARSE_INTEGRATED.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/README_LITEPARSE_INTEGRATED.md) | 集成說明 |

---

## 🧪 測試

### 端到端測試

```bash
py test_end_to_end.py
```

### Docker 測試

```bash
docker-compose ps
docker-compose logs -f
```

---

## 🔧 常見命令

```bash
# 啟動服務
docker-compose up -d

# 查看日誌
docker-compose logs -f

# 停止服務
docker-compose down

# 重建容器
docker-compose build --no-cache

# 進入容器調試
docker-compose exec liteparse-mcp sh
```

---

## ❓ 常見問題

### Q: 需要手動安裝依賴嗎？

**A:** 唔需要！所有依賴已包含喺 Docker 容器入面。

### Q: Docker 容器佔用幾多資源？

**A:** 最多 1.5GB RAM, 1.5 CPU（實際使用更少）

### Q: 點樣上傳 PDF 文件？

**A:** 將 PDF 放入 `data/pdfs/` 目錄，容器會自動掛載。

### Q: 遇到問題點算？

**A:** 查看 [`FIRST_STEP_COMPLETE.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/FIRST_STEP_COMPLETE.md) 嘅常見問題章節。

---

## 🎯 下一步

**第一步 ✅ 已完成** - Docker 化部署，零手動安裝

**下一步：** 第二步（數據清洗與 Prompt 設計）

1. 優化數據清洗邏輯
2. 設計 System Prompt
3. 測試真實場景

---

## 📞 需要幫助？

查看完整文檔：[`FIRST_STEP_COMPLETE.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/FIRST_STEP_COMPLETE.md)

---

**記住：所有依賴已包含喺 Docker 容器入面，你只需要運行 `docker-compose up -d`！** 🚀
