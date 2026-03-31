# PDF 處理和 UI 問題修復 🛠️

## 問題診斷

### 1. PDF 處理失敗 - Java 缺失 ❌
**錯誤信息：** `PDF Conversion Error: [Errno 2] No such file or directory: 'java'`

**根本原因：**
- `opendataloader-pdf` 依賴 Java 運行時進行 PDF 解析
- Docker 容器中未安裝 Java

### 2. UI 選擇框問題 🔧
**症狀：** 選擇框無法正常顯示選中狀態

**可能原因：**
- JavaScript 事件綁定問題
- CSS 樣式衝突

---

## 已完成的修復

### ✅ 修復 1：在 Dockerfile 中安裝 Java

**主 Dockerfile (`nanobot/Dockerfile`)**
```dockerfile
# 第 8-11 行：添加 default-jre-headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    default-jre-headless \  # ← 新增
    && rm -rf /var/lib/apt/lists/*
```

**WebUI Dockerfile (`nanobot/webui/Dockerfile`)**
```dockerfile
# 第 8-14 行：添加 default-jre-headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    default-jre-headless \  # ← 新增
    &rm -rf /var/lib/apt/lists/*
```

### ✅ 修復 2：刪除不必要的 torchaudio

**主 Dockerfile (`nanobot/Dockerfile` 第 30-33 行)**
```dockerfile
# Install CPU-only PyTorch FIRST (before opendataloader)
# Removed torchaudio - not needed for PDF processing (saves ~50MB and build time)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1 \
    torchvision==0.20.1
    # ❌ torchaudio 已刪除
```

---

## 重新 Build 和測試

### 1. 完全重新 Build（清除缓存）
```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot

# 停止所有服務
docker compose down

# 清除 build 缓存（重要！確保 Java 被安裝）
docker builder prune -f

# 重新 build 所有服務
docker compose build --no-cache

# 啟動服務
docker compose up -d
```

### 2. 查看日誌確認 Java 安裝
```bash
# 檢查 nanobot-gateway 日誌
docker compose logs nanobot-gateway | grep -i java

# 檢查 WebUI 日誌
docker compose logs nanobot-webui | grep -i java

# 檢查 ingestion-worker 日誌（如果有啟動）
docker compose logs ingestion-worker
```

### 3. 測試 PDF 上傳和處理

**步驟：**
1. 打開瀏覽器訪問：http://localhost:3000
2. 上傳測試 PDF（建議小於 10MB）
3. 觀察處理日誌：
   - 應該看到 `Processing 3SBIO.pdf: Converting PDF to JSON (20%)`
   - 然後是 `Processing 3SBIO.pdf: Parsing pages (50%)`
   - 最後是 `Processing 3SBIO.pdf: Saving results (90%)`
4. 檢查是否還有 `No such file or directory: 'java'` 錯誤

### 4. 測試 UI 選擇框

**測試步驟：**
1. 進入 **PDF Library** 標籤
2. 點擊任一 PDF 卡片
3. 檢查：
   - ✅ 卡片邊框是否變為藍色（選中狀態）
   - ✅ 右側詳情面板是否打開
   - ✅ 勾選框是否正常勾選/取消

**如果選擇框仍有問題：**
```bash
# 檢查瀏覽器控制台錯誤
# 按 F12 打開開發者工具 → Console 標籤
# 查找 JavaScript 錯誤
```

---

## 預期結果

### ✅ 成功的 PDF 處理日誌
```
[07:30:15] Starting to process: 3SBIO.pdf (ID: 3SBIO_135259d6)
[07:30:16] Processing 3SBIO.pdf: Converting PDF to JSON (20%)
[07:30:20] Processing 3SBIO.pdf: Parsing pages (50%)
[07:30:30] Processing 3SBIO.pdf: Saving results (90%)
[07:30:35] ✅ Successfully processed: 3SBIO.pdf
[07:30:35] 📊 Extracted: 150 chunks, 25 tables, 5 images
```

### ❌ 失敗的日誌（如果 Java 仍未安裝）
```
[07:30:15] ❌ Processing failed for 3SBIO.pdf: PDF Conversion Error: [Errno 2] No such file or directory: 'java'
```

---

## 故障排除

### Q1: Build 後仍有 Java 錯誤？

**解決方案：**
```bash
# 1. 確認 Dockerfile 已保存修改
docker compose config

# 2. 強制重新 build（不使用 cache）
docker compose build --no-cache nanobot-gateway
docker compose build --no-cache nanobot-webui

# 3. 進入容器驗證 Java 是否安裝
docker compose exec nanobot-gateway java -version
docker compose exec nanobot-webui java -version
```

**預期輸出：**
```
openjdk version "17.0.x" 2024-01-16
OpenJDK Runtime Environment (build 17.0.x+xx-Debian-1deb12u1)
OpenJDK 64-Bit Server VM (build 17.0.x+xx-Debian-1deb12u1, mixed mode, sharing)
```

### Q2: UI 選擇框仍然無法正常工作？

**檢查步驟：**

1. **檢查 JavaScript 控制台錯誤**
   ```
   F12 → Console → 查找錯誤
   ```

2. **強制刷新瀏覽器緩存**
   ```
   Ctrl + Shift + R (Windows/Linux)
   Cmd + Shift + R (Mac)
   ```

3. **檢查 library.js 是否正確加載**
   ```
   F12 → Network → 刷新頁面 → 查看 library.js 是否 200 OK
   ```

4. **手動測試選擇功能**
   打開瀏覽器控制台，執行：
   ```javascript
   console.log('Library module:', window.Library);
   console.log('Documents:', Library.documents);
   console.log('Selected Docs:', Library.selectedDocs);
   ```

### Q3: PDF 處理卡住或超時？

**可能原因：**
- PDF 檔案過大（>50MB）
- 頁數過多（>500 頁）
- 記憶體不足

**解決方案：**
```bash
# 增加 Docker 容器記憶體限制
# 編輯 docker-compose.yml，修改 deployment.resources.limits.memory

# 查看容器資源使用情況
docker stats nanobot-gateway nanobot-webui
```

---

## 性能優化建議

### 1. 使用 Docker Build Cache
第一次 build 後，後續 build 會快很多：
```bash
# 第一次（慢）
docker compose build --no-cache  # ~2-3 分鐘

# 後續（快）
docker compose build  # ~10-20 秒（使用 cache）
```

### 2. 分離 PDF 處理 worker
如果經常需要處理大量 PDF，建議啟動專用的 ingestion worker：
```bash
# 啟動 worker 服務
docker compose --profile worker up -d ingestion-worker
```

### 3. 監控處理進度
```bash
# 實時查看處理日誌
docker compose logs -f ingestion-worker

# 查看數據庫存入情況
docker compose exec postgres-financial psql -U postgres -d annual_reports -c "SELECT COUNT(*) FROM document_chunks;"
```

---

## 總結

### 已完成的修改：
1. ✅ 在 **nanobot/Dockerfile** 中安裝 `default-jre-headless`
2. ✅ 在 **nanobot/webui/Dockerfile** 中安裝 `default-jre-headless`
3. ✅ 刪除不必要的 `torchaudio`（節省 ~50MB 和 build 時間）
4. ✅ 更新 Vanna Service 支持「邊做邊學」

### 下一步：
1. 重新 build Docker 鏡像
2. 測試 PDF 上傳和處理
3. 驗證 UI 選擇框功能
4. 測試 Vanna 自動訓練功能

### 參考文檔：
- [Vanna Service 升級文檔](./VANNA_SERVICE_UPGRADE.md)
- [WebUI README](./webui/README_REFACTORED.md)
- [快速啟動指南](./webui/QUICK_START.md)

---

**祝測試順利！** 🚀

如果仍有問題，請提供：
1. `docker compose logs` 完整輸出
2. 瀏覽器控制台截圖（F12）
3. 測試的 PDF 檔案大小和頁數
