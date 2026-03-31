# Bug Fixes Summary

## 修復日期：2026-03-31

本文檔總結了所有已修復的 WebUI 和後端問題。

---

## 🐛 問題 1: 圖片 (JPG) 沒有被儲存

**位置:** `nanobot/ingestion/opendataloader_processor.py`

**問題描述:** 
在 `_save_image` 函數中，實際寫入圖片二進位資料的程式碼被註解掉了，取而代之的是使用 `image_path.touch()` 建立了一個空檔案（0 bytes）。

**修復方案:**
- 解鎖圖片儲存邏輯，當 `image_data` 存在時寫入真實的二進制數據
- 添加日誌記錄以便調試

**修改內容:**
```python
# 解鎖前（被註解）
# TODO: 當 image_data 為真實二進制時解鎖
# with open(image_path, 'wb') as f:
#     f.write(image_data)
image_path.touch()

# 解鎖後
if image_data:
    with open(image_path, 'wb') as f:
        f.write(image_data)
    logger.debug(f"💾 圖片已保存：{image_path.name} ({len(image_data)} bytes)")
else:
    logger.warning(f"⚠️ 圖片數據為空，跳過保存：{image_path.name}")
    image_path.touch()
```

---

## 🐛 問題 2: Output Preview 長期開啟無法關閉

**位置:** `webui/static/js/library.js`

**問題描述:** 
點擊關閉按鈕時只隱藏了彈出視窗（`json-output-modal`），忘記隱藏詳細面板中的預覽區塊（`processed-output-preview`）。

**修復方案:**
在 `closeJsonModal()` 函數中添加一行來隱藏預覽區塊。

**修改內容:**
```javascript
closeJsonModal() {
    document.getElementById('json-output-modal').classList.add('hidden');
    // 新增：隱藏詳細面板中的預覽區塊
    document.getElementById('processed-output-preview').classList.add('hidden');
    this.currentJsonOutput = null;
}
```

---

## 🐛 問題 3: Checkbox 損壞 (無法正常選取)

**位置:** `webui/static/js/library.js`

**問題描述:** 
當有文件在處理時，`startStatusPolling()` 會每 2 秒呼叫一次 `Library.loadDocuments()`，進而觸發 `renderGrid()`。而 `renderGrid()` 會直接使用 `innerHTML = ''` 清空整個網格並重新生成所有 DOM 元素，導致 Checkbox 被銷毀並重新創建，使用者無法順利點擊。

**修復方案:**
優化 `renderGrid()` 函數，實現增量更新：
1. 如果文件數量沒有改變，只更新進度條和狀態，不重繪整個 DOM
2. 添加 `_createDocumentCard()` 方法來創建單個卡片
3. 添加 `_updateDocumentCard()` 方法來增量更新卡片狀態

**修改內容:**
- 完全重繪只在文件數量改變時發生
- 輪詢時只更新進度條寬度和百分比文本
- Checkbox 狀態保持不變，不會被強制重置

---

## 🐛 問題 4: Chat Tab Session 損壞

**位置:** 
- `webui/static/js/ui.js`
- `webui/static/js/api.js`
- `webui/app/api/chat.py`
- `webui/app/schemas/chat.py`
- `webui/app/services/chat_service.py`

**問題描述:**
1. 前端沒有傳遞 Session ID，每次對話都是全新的請求，後端無法追蹤對話上下文
2. 雖然介面上可以透過 `tagDocument` 把 `[Doc: /path]` 插入輸入框，但實際送出請求時沒有解析並傳遞 `document_path` 參數

**修復方案:**

### 前端修改 (`ui.js`):
```javascript
// 添加 Session ID 狀態
chatSessionId: null,

// 在 handleChatSubmit 中
// 1. 生成 Session ID（如果還沒有的話）
if (!this.chatSessionId) {
    this.chatSessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

// 2. 解析文件路徑
let docPath = null;
const docMatch = message.match(/\[Doc:\s([^\]]+)\]/);
if (docMatch) {
    docPath = docMatch[1];
}

// 3. 傳遞 sessionId 和 docPath
const response = await API.chatStream(message, Auth.getUser(), docPath, this.chatSessionId);
```

### API 修改 (`api.js`):
```javascript
async chatStream(message, username, documentPath = null, sessionId = null) {
    const response = await fetch(`${this.BASE_URL}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            message: message,
            username: username,
            document_path: documentPath,
            session_id: sessionId
        })
    });
    return response;
}
```

### 後端 Schema 修改 (`chat.py`, `schemas/chat.py`):
```python
# 添加 ChatStreamRequest schema
class ChatStreamRequest(BaseModel):
    message: str
    username: str = "anonymous"
    document_path: Optional[str] = None
    session_id: Optional[str] = None

# 添加 stream 端點
@router.post("/stream")
async def chat_stream_endpoint(request: ChatStreamRequest):
    async def generate():
        reply_text = await process_chat_message(
            request.message,
            request.username,
            request.document_path,
            request.session_id
        )
        yield f"data: {json.dumps({'content': reply_text})}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")
```

### 服務層修改 (`chat_service.py`):
```python
async def process_chat_message(
    user_message: str, 
    username: str = "anonymous", 
    document_path: Optional[str] = None,
    session_id: Optional[str] = None
) -> str:
    # 使用 session_id 作為 chat_id
    response = await client.post(
        f"{NANOBOT_API_URL}/api/chat",
        json={
            "message": user_message,
            "username": username,
            "chat_id": session_id or "webui-session",
            "user_id": username,
        }
    )
```

---

## ✨ 新增功能：ZIP 打包下載所有 Raw Output

**位置:** 
- `webui/app/api/document.py`
- `webui/static/js/library.js`
- `webui/static/js/api.js`

**功能描述:**
新增端點 `/api/pdf/{doc_id}/output/download-all`，將 `DATA_DIR` 內該 `doc_id` 目錄下的所有 `.json` 表格檔和 `.png/.jpg` 圖片檔打包成一個 `.zip` 壓縮檔回傳給使用者。

**實現內容:**

### 後端 (`document.py`):
```python
@router.get("/pdf/{doc_id}/output/download-all")
async def download_all_raw_output(doc_id: str):
    """Download all raw output (JSON tables + images) as a ZIP file."""
    data_dir = document_service.output_dir / doc_id
    
    if not data_dir.exists():
        raise HTTPException(status_code=404, detail="No raw output found")
    
    # 收集所有文件
    files_to_include = list(data_dir.rglob("*"))
    
    # 創建 ZIP 文件（內存中）
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in files_to_include:
            arcname = file_path.relative_to(data_dir)
            zip_file.write(file_path, arcname=str(arcname))
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={doc['filename']}_raw_output.zip"}
    )
```

### 前端 (`library.js`, `api.js`):
```javascript
// library.js
downloadProcessedOutput() {
    if (!this.selectedDocument) return;
    this.log(`Downloading all raw output (ZIP)...`);
    window.location.href = API.getAllRawOutputDownloadUrl(this.selectedDocument.id);
}

// api.js
getAllRawOutputDownloadUrl(docId) {
    return `${this.BASE_URL}/api/pdf/${docId}/output/download-all`;
}
```

---

## 📋 測試清單

### 圖片儲存測試
- [ ] 上傳包含圖片的 PDF 文件
- [ ] 檢查 `data/{doc_id}/` 目錄下是否生成非空的 `.png` 或 `.jpg` 文件
- [ ] 驗證圖片文件大小 > 0 bytes

### Output Preview 關閉測試
- [ ] 點擊 "View Output" 按鈕
- [ ] 確認彈出視窗和預覽區塊都顯示
- [ ] 點擊關閉按鈕 (X)
- [ ] 確認彈出視窗和預覽區塊都隱藏

### Checkbox 穩定性測試
- [ ] 上傳多個 PDF 文件
- [ ] 在處理過程中嘗試勾選多個文件的 Checkbox
- [ ] 確認 Checkbox 不會被自動取消勾選
- [ ] 確認可以正常使用批量操作功能

### Chat Session 測試
- [ ] 開啟 Chat Tab
- [ ] 發送第一條消息（不帶文件標籤）
- [ ] 發送第二條消息，確認後端能追蹤同一 Session
- [ ] 點擊 sidebar 中的文件標籤文件
- [ ] 發送帶 `[Doc: filename.pdf]` 標籤的消息
- [ ] 確認後端收到正確的 `document_path` 參數

### ZIP 下載測試
- [ ] 選擇已完成處理的文件
- [ ] 點擊 "Download" 按鈕（在 View Output 面板中）
- [ ] 確認下載的文件名為 `{filename}_raw_output.zip`
- [ ] 解壓縮 ZIP 文件
- [ ] 確認包含所有 `.json` 表格文件和 `.png/.jpg` 圖片文件

---

## 🔧 相關文件清單

### 後端文件
- `nanobot/ingestion/opendataloader_processor.py`
- `webui/app/api/document.py`
- `webui/app/api/chat.py`
- `webui/app/schemas/chat.py`
- `webui/app/services/chat_service.py`
- `webui/app/services/pdf_service.py`

### 前端文件
- `webui/static/js/library.js`
- `webui/static/js/ui.js`
- `webui/static/js/api.js`
- `webui/static/js/app.js`

---

## 📝 備註

1. **圖片儲存**：目前 `_parse_with_opendataloader` 函數中，圖片的 `image_data` 仍然是空的 (`b""`)，需要確保 OpenDataLoader 返回真實的圖片二進制數據才能真正保存圖片。

2. **Session 管理**：目前的 Session ID 是前端生成的臨時 ID，存儲在內存中。刷新頁面後會丟失。如果需要持久化 Session，可以考慮使用 localStorage 或後端 Session。

3. **增量更新**：`_updateDocumentCard` 方法目前只更新進度條和 Checkbox，如果需要更新其他動態內容（如狀態徽章），需要額外添加邏輯。

4. **ZIP 下載**：對於大型文件（數百 MB），在內存中創建 ZIP 可能會消耗大量 RAM。未來可以考慮使用流式 ZIP 壓縮或臨時文件方式。

---

## 🚀 下一步建議

1. **測試所有修復**：按照測試清單逐一驗證所有修復是否生效
2. **監控日誌**：檢查服務器日誌，確認沒有新的錯誤
3. **用戶反饋**：收集用戶使用反饋，確認問題是否真正解決
4. **性能優化**：如果需要處理大量並發上傳，考慮優化 ZIP 壓縮策略
5. **Session 持久化**：如果需要，實現後端 Session 管理

---

**修復完成時間:** 2026-03-31 16:05 GMT+8
**修復者:** AI Assistant
