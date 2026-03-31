# Docker Volume 配置指南

本專案使用 Docker 容器來運行所有服務，數據存儲是一個關鍵問題。本文檔說明如何選擇合適的 Volume 配置策略。

---

## 📋 兩種 Volume 策略

### 1. 綁定掛載 (Bind Mount) - 同步到本機

在 `docker-compose.yml` 中這樣寫：
```yaml
services:
  nanobot-webui:
    volumes:
      - ./data:/app/data          # 本機專案目錄/data → 容器/app/data
      - ./webui/uploads:/app/uploads
      - ./postgres_data:/var/lib/postgresql/data
```

**特點：**
- ✅ **開發除錯友善**：可以直接用 VSCode 或檔案總管打開容器生成的文件
- ✅ **即時預覽**：PDF 解析後的 JSON、圖片等，可以立即在本地查看
- ✅ **方便備份**：只要備份本機的 `./data` 目錄即可
- ❌ **污染專案目錄**：本機目錄會出現大量生成的數據文件
- ❌ **效能較差**：在 Windows/Mac 上，Bind Mount 的讀寫效能比 Linux 低
- ❌ **權限問題**：可能出現容器內寫入後，本地無法讀取的權限問題

**適用階段：** 開發、除錯、測試期

---

### 2. 具名卷冊 (Named Volume) - Docker 專用空間

在 `docker-compose.yml` 中這樣寫：
```yaml
services:
  nanobot-webui:
    volumes:
      - webui_data:/app/data      # Docker 管理的隱藏空間

volumes:
  webui_data:                     # 在檔案底部宣告
```

**特點：**
- ✅ **專案目錄整潔**：完全不會污染本地專案資料夾
- ✅ **效能最佳**：Docker 原生管理，讀寫效能最好
- ✅ **跨平台相容**：沒有 Windows/Mac/Linux 的權限差異
- ✅ **生產環境首選**：適合部署到伺服器
- ❌ **除錯不便**：無法直接用檔案總管查看，必須進入容器 (`docker exec`)
- ❌ **備份麻煩**：需要使用 `docker volume` 命令來備份

**適用階段：** 生產環境、上線部署

---

## 🎯 本專案的建議配置

### 當前配置（開發除錯期）

目前 `docker-compose.yml` 使用的是 **綁定掛載 (Bind Mount)**：

```yaml
services:
  # PostgreSQL Database
  postgres-financial:
    volumes:
      - postgres_data:/var/lib/postgresql/data  # Named Volume (資料庫建議用 Named)
      - ./storage/init_complete.sql:/docker-entrypoint-initdb.d/init.sql

  # Web UI
  nanobot-webui:
    volumes:
      - pdf_upload_data:/app/uploads            # Named Volume
      - ./webui/uploads:/app/uploads            # Bind Mount (覆蓋 Named)
      - ./webui/outputs:/app/outputs
      - ./data/raw:/app/data/raw
      - ./nanobot:/app/nanobot:ro

  # Ingestion Worker
  ingestion-worker:
    volumes:
      - ./data/raw:/app/data/raw
```

**策略說明：**
1. **PostgreSQL 數據**：使用 Named Volume (`postgres_data`)，避免資料庫文件污染專案
2. **WebUI 上傳/輸出**：同時使用 Bind Mount 和 Named Volume，Bind Mount 優先
3. **Raw 數據**：使用 Bind Mount (`./data/raw`)，方便查看 OpenDataLoader 的輸出

---

## ⚠️ 重要：.gitignore 配置

使用 Bind Mount 時，**必須**確保生成的數據文件不會被提交到 Git。

已更新的 `.gitignore`：

```gitignore
# ===========================================
# Docker Data Volumes - DO NOT COMMIT
# ===========================================
# Generated PDF data
data/
webui/uploads/
webui/outputs/
webui/data/

# PostgreSQL data
postgres_data/

# Vanna training data
vanna_data/
vanna-service/data/

# Raw extracted data
data/raw/

# Processing outputs
**/outputs/
**/uploads/

# ===========================================
# Development artifacts
# ===========================================
*.log
logs/
*.tmp
*.temp
```

**驗證方法：**
```bash
# 檢查是否有未追蹤的文件
git status

# 應該看到這些目錄出現在 "Untracked files" 中
# 確保它們不會被 git add . 加入
```

---

## 🔄 未來轉換為純 Named Volume

當你完成除錯，準備部署時，可以改為純 Named Volume 配置：

### 修改步驟

**1. 編輯 `docker-compose.yml`：**

```yaml
services:
  nanobot-webui:
    volumes:
      - webui_data:/app/data     # 改為 Named Volume
      - webui_outputs:/app/outputs

  ingestion-worker:
    volumes:
      - worker_data:/app/data/raw

volumes:
  webui_data:
  webui_outputs:
  worker_data:
  # postgres_data 已存在
```

**2. 遷移現有數據（可選）：**

```bash
# 停止所有服務
docker-compose down

# 從 Bind Mount 複製數據到 Named Volume
docker run --rm \
  -v $(pwd)/data:/source \
  -v webui_data:/dest \
  alpine cp -r /source/. /dest/

# 重新啟動
docker-compose up -d
```

**3. 清理本地目錄：**

```bash
# 刪除本地生成的數據目錄
rm -rf data/ webui/uploads/ webui/outputs/
```

---

## 📊 對比總結

| 特性 | Bind Mount | Named Volume |
|------|------------|--------------|
| 專案目錄整潔 | ❌ 污染 | ✅ 整潔 |
| 除錯便利性 | ✅ 方便 | ❌ 不便 |
| 讀寫效能 | ⚠️ 普通 (Win/Mac) | ✅ 最佳 |
| 權限問題 | ⚠️ 可能有 | ✅ 無 |
| 備份難度 | ✅ 簡單 | ⚠️ 需命令 |
| 適用階段 | 開發/除錯 | 生產/部署 |

---

## 🚀 快速檢查清單

### 開發階段（現在）
- [x] 使用 Bind Mount 方便查看輸出
- [x] `.gitignore` 已排除 `data/`、`outputs/` 等目錄
- [ ] 定期檢查 `git status` 確認沒有誤提交數據文件

### 部署階段（未來）
- [ ] 改為 Named Volume 配置
- [ ] 遷移現有數據（如需要）
- [ ] 清理本地目錄
- [ ] 更新部署文檔

---

## 🛠️ 常用命令

### 查看 Volume
```bash
# 列出所有 Volume
docker volume ls

# 查看 Volume 詳情
docker volume inspect webui_data
```

### 進入容器查看數據
```bash
# 進入 WebUI 容器
docker exec -it nanobot-webui bash

# 查看數據
ls -la /app/data
cat /app/data/raw/some_file.json
```

### 備份 Volume
```bash
# 備份 Named Volume 到 tar.gz
docker run --rm \
  -v nanobot_webui_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/webui_data_backup.tar.gz -C /data .
```

### 還原 Volume
```bash
# 從 tar.gz 還原
docker run --rm \
  -v nanobot_webui_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/webui_data_backup.tar.gz -C /data
```

---

## 📝 總結建議

**現在（開發除錯期）：**
- ✅ 保持 Bind Mount 配置
- ✅ 確保 `.gitignore` 正確
- ✅ 專注於修復 OpenDataLoader 和 PDF 處理問題

**未來（生產部署）：**
- 🔄 改為 Named Volume
- 🔄 清理本地目錄
- 🔄 優化效能和安全性

**關鍵原則：**
> 程式碼不會知道你是用哪種 Volume，它看到的永遠是 `/app/data`。
> 選擇的標準是：**什麼階段用什麼策略**，不要一成不變。

---

**文檔更新日期：** 2026-03-31  
**適用版本：** v2.1.1
