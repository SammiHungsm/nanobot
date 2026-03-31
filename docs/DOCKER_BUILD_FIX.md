# WebUI Docker Build 修復指南 - 2026-03-31

## 🔴 問題：Docker Build Context 錯誤

**錯誤訊息：**
```
"/bridge": not found
```

**根本原因：**
Docker Build Context 設定錯誤。`nanobot-webui` 的 build context 原本設定為 `./webui`，導致 Docker 只能看到 `webui/` 資料夾內的內容。當 Dockerfile 試圖使用 `COPY ../bridge/` 往上一層抓取檔案時，Docker 找不到這個路徑。

---

## ✅ 修復方案

### 步驟 1：修改 `docker-compose.yml`

將 `nanobot-webui` 的 build context 提升到專案根目錄：

```yaml
nanobot-webui:
  build:
    context: .                    # 原本是 ./webui，改為 . (根目錄)
    dockerfile: webui/Dockerfile  # 明確指定 Dockerfile 路徑
```

**修改的文件：** [`docker-compose.yml`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/docker-compose.yml)

---

### 步驟 2：修改 `webui/Dockerfile`

因為 build context 改為根目錄，所有 `COPY` 指令的路徑都必須以根目錄為起點：

**原本的寫法（錯誤）：**
```dockerfile
COPY requirements.txt .
COPY ../nanobot/ /tmp/nanobot/
COPY ../pyproject.toml /tmp/nanobot/
COPY ../bridge/ /tmp/nanobot/bridge/
COPY app/ ./app/
COPY static/ ./static/
```

**修正後的寫法（正確）：**
```dockerfile
COPY webui/requirements.txt .
COPY nanobot/ /tmp/nanobot/
COPY pyproject.toml /tmp/nanobot/
COPY README.md /tmp/nanobot/
COPY bridge/ /tmp/nanobot/bridge/
COPY webui/app/ ./app/
COPY webui/static/ ./static/
```

**修改的文件：** [`webui/Dockerfile`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/webui/Dockerfile)

---

## 💡 為什麼這樣改就會好？

改變 Context 為 `.` 後：

1. **Docker 引擎會把整個 `sfc_poc/nanobot` 目錄打包**送給 Daemon
2. Docker 現在可以順利讀取到：
   - `webui/requirements.txt`
   - `nanobot/` 目錄
   - `pyproject.toml`
   - `bridge/` 目錄
   - `webui/app/` 和 `webui/static/`
3. **不再需要 `../`** 這種相對路徑，所有路徑都從根目錄開始

---

## 🚀 重新部署

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot

# 1. 停止當前服務
docker-compose down nanobot-webui

# 2. 重新構建（使用 --no-cache 確保完全重建）
docker-compose build --no-cache nanobot-webui

# 3. 啟動服務
docker-compose up -d nanobot-webui

# 4. 查看 Log 確認成功
docker logs nanobot-webui -f
```

**預期的成功 Log：**
```
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

---

## 📊 修復前後對比

| 項目 | 修復前 | 修復後 |
|------|--------|--------|
| Build Context | `./webui` | `.` (根目錄) |
| Dockerfile 路徑 | 使用 `../` | 使用 `webui/` 前綴 |
| 可見範圍 | 只能看到 `webui/` | 可以看到整個專案 |
| 結果 | ❌ Build 失敗 | ✅ Build 成功 |

---

## 📝 完整修改清單

### 1. docker-compose.yml
```diff
  nanobot-webui:
    build:
-     context: ./webui
-     dockerfile: Dockerfile
+     context: .
+     dockerfile: webui/Dockerfile
```

### 2. webui/Dockerfile
```diff
- COPY requirements.txt .
+ COPY webui/requirements.txt .

- COPY ../nanobot/ /tmp/nanobot/
- COPY ../pyproject.toml /tmp/nanobot/
- COPY ../README.md /tmp/nanobot/
- COPY ../bridge/ /tmp/nanobot/bridge/
+ COPY nanobot/ /tmp/nanobot/
+ COPY pyproject.toml /tmp/nanobot/
+ COPY README.md /tmp/nanobot/
+ COPY bridge/ /tmp/nanobot/bridge/

- COPY app/ ./app/
+ COPY webui/app/ ./app/

- COPY static/ ./static/
+ COPY webui/static/ ./static/
```

---

## ⚠️ 重要提醒

### .gitignore 配置

確保以下目錄不會被提交到 Git：

```gitignore
# Docker Data Volumes
data/
webui/uploads/
webui/outputs/
postgres_data/
vanna_data/
```

已更新的文件： [`.gitignore`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/.gitignore)

### Volume 配置策略

- **開發期**：使用 Bind Mount（方便除錯）
- **生產期**：改用 Named Volume（保持整潔）

詳細說明請參考：[`VOLUME_GUIDE.md`](file:///C:/Users/sammi_hung/Desktop/SFC_AI/sfc_poc/nanobot/VOLUME_GUIDE.md)

---

## ✅ 完成清單

- [x] 修改 `docker-compose.yml` 將 build context 改為根目錄
- [x] 修改 `webui/Dockerfile` 更新所有 COPY 路徑
- [x] 更新 `.gitignore` 排除生成的數據文件
- [x] 創建 `VOLUME_GUIDE.md` 說明 Volume 配置策略

---

## 🔍 故障排查

### 如果 Build 仍然失敗

1. **清除 Docker 快取：**
   ```bash
   docker-compose build --no-cache nanobot-webui
   ```

2. **檢查文件是否存在：**
   ```bash
   # 確認這些文件在專案根目錄存在
   ls -la nanobot/
   ls -la bridge/
   ls -la pyproject.toml
   ls -la README.md
   ```

3. **檢查 Docker 版本：**
   ```bash
   docker --version
   docker-compose --version
   ```

### 如果容器啟動後立即退出

查看完整 Log：
```bash
docker logs nanobot-webui --tail 200
```

常見問題：
- 資料庫連接失敗 → 確認 `DATABASE_URL` 正確
- Gateway 連接失敗 → 確認 `nanobot-gateway` 服務正在運行
- 權限問題 → 檢查 volume 掛載的目錄權限

---

**修復完成日期：** 2026-03-31  
**修復版本：** v2.1.2  
**關鍵修改：** Docker Build Context + Dockerfile 路徑修正
