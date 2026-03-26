# 🐳 LiteParse MCP Server - Docker 部署指南

> **所有依賴已包含喺 Docker 容器入面，無需用戶手動安裝！** 🎉

---

## 🚀 一分鐘快速開始

### 步驟 1：啟動服務

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot
docker-compose up -d
```

### 步驟 2：確認運行狀態

```bash
docker-compose ps
```

應該見到：
```
NAME                STATUS              PORTS
liteparse-mcp       Up                  3000/tcp
nanobot-gateway     Up                  18790/tcp, 0.0.0.0:8080->8080/tcp
```

### 步驟 3：查看日誌

```bash
docker-compose logs -f
```

### 步驟 4：停止服務

```bash
docker-compose down
```

**就係咁簡單！** 無需要安裝 Node.js、Python、或者任何依賴。🎉

---

## 📦 Docker 容器包含咩？

### `liteparse-mcp` 容器

| 組件 | 版本 | 用途 |
|------|------|------|
| Node.js | 20.x | 運行 MCP Server |
| LiteParse CLI | latest | PDF 解析 |
| Python | 3.11 | 數據清洗層 |
| PyMuPDF | latest | PDF 處理 |
| Pillow | latest | 圖像處理 |
| MCP SDK | ^1.0.4 | Model Context Protocol |

### `nanobot-gateway` 容器

| 組件 | 版本 | 用途 |
|------|------|------|
| Python | 3.11 | Nanobot 主程式 |
| Nanobot | latest | Agent 框架 |
| MCP Client | built-in | 連接 LiteParse |

---

## 🔧 環境配置

### 環境變量

如果需要自定義配置，可以修改 [`docker-compose.yml`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/docker-compose.yml)：

```yaml
services:
  nanobot-gateway:
    environment:
      - MINIMAX_API_KEY=your-api-key-here
      - NANOBOT_CONFIG=/app/config/config.json
```

### 自定義配置

將配置文件放在 [`config/`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/config) 目錄：

```bash
# 複製範例配置
cp config/config.json.example config/config.json

# 編輯配置
# 然後重啟容器
docker-compose restart nanobot-gateway
```

---

## 📁 數據存儲

### PDF 文件位置

將 PDF 文件放在以下目錄，Docker 會自動掛載：

```
C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\data\pdfs\
```

容器內的路徑：`/data/pdfs/`

### 日誌文件

日誌會自動保存在：

```
C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\.data\logs\
```

---

## 🧪 測試與調試

### 測試容器連接

```bash
# 測試 LiteParse MCP Server
docker-compose exec liteparse-mcp node -e "console.log('MCP Server OK')"

# 測試 LiteParse CLI
docker-compose exec liteparse-mcp lit --version

# 測試 Python Data Cleaner
docker-compose exec liteparse-mcp python --version
```

### 查看容器日誌

```bash
# 查看所有容器日誌
docker-compose logs -f

# 只看 LiteParse 日誌
docker-compose logs -f liteparse-mcp

# 只看 Nanobot 日誌
docker-compose logs -f nanobot-gateway
```

### 進入容器調試

```bash
# 進入 LiteParse 容器
docker-compose exec liteparse-mcp sh

# 進入 Nanobot 容器
docker-compose exec nanobot-gateway sh
```

---

## 🔄 更新與重建

### 更新到最新版本

```bash
# 拉取最新代碼
git pull

# 重建容器（使用緩存）
docker-compose build

# 重啟服務
docker-compose up -d
```

### 強制重建（無緩存）

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## ❓ 常見問題

### Q1: 點解要用 Docker？

**A:** Docker 提供以下好處：

1. **零依賴安裝** - 無需要手動安裝 Node.js、Python、LiteParse
2. **環境隔離** - 唔會同系統其他軟件衝突
3. **可重現性** - 確保開發、測試、生產環境一致
4. **一鍵部署** - `docker-compose up -d` 就搞定
5. **易於清理** - `docker-compose down` 就乾淨曬

### Q2: Docker 容器佔用幾多資源？

**A:** 根據 [`docker-compose.yml`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/docker-compose.yml) 配置：

- **LiteParse MCP**: 最多 512MB RAM, 0.5 CPU
- **Nanobot Gateway**: 最多 1GB RAM, 1 CPU
- **總計**: 最多 1.5GB RAM, 1.5 CPU

實際使用通常遠低於呢個限制。

### Q3: 點樣備份數據？

**A:** Docker 容器係無狀態嘅，所有數據保存在掛載嘅 volume：

```bash
# 備份配置
tar -czf nanobot-config-backup.tar.gz config/

# 備份日誌
tar -czf nanobot-logs-backup.tar.gz .data/logs/
```

### Q4: 遇到端口衝突點算？

**A:** 修改 [`docker-compose.yml`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/docker-compose.yml) 嘅端口映射：

```yaml
services:
  nanobot-gateway:
    ports:
      - "18791:18790"  # 改為其他端口
      - "8081:8080"
```

### Q5: Docker 容器啟動失敗點算？

**A:** 跟呢個順序排查：

1. **檢查 Docker 狀態**: `docker ps`
2. **查看錯誤日誌**: `docker-compose logs`
3. **檢查配置文件**: `docker-compose config`
4. **重建容器**: `docker-compose down && docker-compose build`
5. **檢查端口佔用**: `netstat -ano | findstr :3000 :8080`

---

## 📊 Docker Compose 配置解析

### LiteParse MCP 服務

```yaml
liteparse-mcp:
  build:
    context: ./liteparse-mcp-server
    dockerfile: Dockerfile
  volumes:
    - ./data/pdfs:/data/pdfs  # 掛載 PDF 目錄
  networks:
    - default
  restart: unless-stopped  # 自動重啟
  deploy:
    resources:
      limits:
        cpus: '0.5'
        memory: 512M
```

### Nanobot Gateway 服務

```yaml
nanobot-gateway:
  container_name: nanobot-gateway
  build:
    context: .
    dockerfile: Dockerfile
  volumes:
    - ./config:/app/config  # 掛載配置
    - ~/.nanobot:/root/.nanobot  # 掛載用戶數據
  ports:
    - 18790:18790  # Agent 端口
    - 8080:8080    # Web UI 端口
  environment:
    - MINIMAX_API_KEY=...  # API 密鑰
  depends_on:
    - liteparse-mcp  # 依賴 LiteParse
  restart: unless-stopped
```

---

## 🎯 下一步

1. ✅ **啟動服務**: `docker-compose up -d`
2. ✅ **測試連接**: `docker-compose logs -f`
3. ✅ **上傳 PDF**: 將財報 PDF 放入 `data/pdfs/`
4. ✅ **開始對話**: 透過 Nanobot Web UI 或者 API 調用

---

## 📞 需要幫助？

- **查看完整文檔**: [`QUICKSTART_MCP.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/QUICKSTART_MCP.md)
- **實施細節**: [`IMPLEMENTATION_ZH.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/IMPLEMENTATION_ZH.md)
- **Docker 官方文檔**: https://docs.docker.com/compose/

**記住：所有依賴已經包含喺 Docker 容器入面，你只需要運行 `docker-compose up -d`！** 🚀
