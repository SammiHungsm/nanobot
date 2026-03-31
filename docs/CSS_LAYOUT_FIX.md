# CSS Layout Fix - Sidebar and Main Chat Area

## 🐛 問題描述

**時間：** 2026-03-31 16:12 GMT+8

側邊欄（Nanobot Financial Workspace）和主聊天區域（Financial Analysis Chat）從原本的水平並排變成了**垂直堆疊**，導致版面嚴重錯亂。

### 問題截圖
側邊欄跑到最上方，主聊天區域在下方，兩者垂直排列而非水平並排。

---

## 🔍 問題分析

### 根本原因
在 `webui/static/index.html` 中，Chat Tab 的主容器 `#content-chat` 使用了錯誤的 Flexbox 方向：

```html
<!-- ❌ 錯誤：使用 flex-col 導致垂直排列 -->
<div id="content-chat" class="flex-1 flex flex-col h-full">
    <aside class="sidebar">...</aside>
    <main class="main-chat">...</main>
</div>
```

### 為什麼會這樣？
- `flex-col` = 垂直排列（column direction）
- `flex-row` = 水平排列（row direction）

當使用 `flex-col` 時，內部的 `<aside>` 和 `<main>` 元素會變成垂直堆疊，而不是預期的左右並排。

---

## ✅ 修復方案

### 修改文件
**檔案：** `webui/static/index.html`

### 修復內容
將 `#content-chat` 的 class 從 `flex-col` 改為 `flex-row`：

```html
<!-- ✅ 正確：使用 flex-row 實現水平並排 -->
<div id="content-chat" class="flex-1 flex flex-row h-full overflow-hidden">
    <!-- 左側邊欄 -->
    <aside class="w-72 bg-slate-900 text-white flex flex-col border-r border-slate-700/50">
        ...
    </aside>
    
    <!-- 右側主聊天區 -->
    <main class="flex-1 flex flex-col h-full relative">
        ...
    </main>
</div>
```

### 關鍵改變
| 修改前 | 修改後 |
|--------|--------|
| `flex-col` | `flex-row` |
| （無） | `overflow-hidden` |

**說明：**
- `flex-row`：強制內部的 `<aside>` 和 `<main>` 水平並排
- `overflow-hidden`：防止內容溢出導致滾動條異常

---

## 📋 結構說明

### 完整的 Flexbox 層級結構

```
body (flex-col)
└── Main Container (flex-col)
    ├── Tab Navigation
    └── Tab Content Container (flex-1 flex)
        ├── #content-chat (flex-row) ← 修復點
        │   ├── Sidebar (w-72, flex-col)
        │   └── Main Chat (flex-1, flex-col)
        │
        └── #content-library (flex-col) ← 原本就正確
            ├── Header
            └── Library Content (flex)
                ├── Grid (flex-1)
                └── Process Log (w-80)
```

### CSS Flexbox 屬性解釋

```css
/* 父容器：水平排列 */
.chat-layout-wrapper {
    display: flex;        /* 啟用 Flexbox */
    flex-direction: row;  /* 水平排列（Tailwind: flex-row）*/
    height: 100%;         /* 填滿高度 */
    overflow: hidden;     /* 防止溢出 */
}

/* 左側邊欄：固定寬度 */
.sidebar {
    width: 280px;         /* Tailwind: w-72 */
    flex-shrink: 0;       /* 不被壓縮 */
}

/* 右側主區域：佔據剩餘空間 */
.main-chat {
    flex-grow: 1;         /* Tailwind: flex-1 */
    display: flex;
    flex-direction: column; /* 內部垂直排列 */
}
```

---

## 🧪 測試清單

### 視覺測試
- [ ] 側邊欄和主聊天區域水平並排
- [ ] 側邊欄固定在左側，寬度約 280px
- [ ] 主聊天區域佔據剩餘空間
- [ ] 沒有出現水平滾動條
- [ ] 調整瀏覽器視窗大小時版面正常

### 功能測試
- [ ] 側邊欄可以正常滾動（當文件列表過長時）
- [ ] 主聊天區域可以正常滾動
- [ ] Chat Tab 和 Library Tab 切換正常
- [ ] Library Tab 的版面也正常（如有問題需另外修復）

### 響應式測試
- [ ] 在不同螢幕尺寸下測試（桌面、平板、手機）
- [ ] 確認沒有版面錯位或內容溢出

---

## 🛠️ 相關文件

### 已修改
- ✅ `webui/static/index.html` - 修復 `#content-chat` 的 flex 方向

### 相關 CSS 文件（如有需要可進一步優化）
- `webui/static/css/style.css` - 自定義樣式（本次未修改）

---

## 📝 筆記

### 為什麼 Library Tab 沒事？
Library Tab (`#content-library`) 的結構是：
```html
<div id="content-library" class="flex-1 flex flex-col h-full hidden">
    <header>...</header>
    <div class="flex-1 flex overflow-hidden">
        <div class="flex-1 flex flex-col">Grid</div>
        <div class="w-80">Log Panel</div>
    </div>
</div>
```

Library Tab 在內層有一個獨立的 `div class="flex-1 flex overflow-hidden"` 容器，這個容器預設就是 `flex-row`（因為沒有指定 `flex-col`），所以左右兩個區域能正常水平並排。

### 最佳實踐建議

1. **統一使用 Tailwind class**
   - 盡量使用 Tailwind 的 utility class 而非自定義 CSS
   - 保持一致性，避免混用

2. **明確標示 flex 方向**
   - `flex-row` = 水平並排
   - `flex-col` = 垂直堆疊
   - 不要依賴預設值，明確指定更清晰

3. **添加 overflow 控制**
   - 在 flex 容器上添加 `overflow-hidden` 防止內容溢出
   - 在需要滾動的區域使用 `overflow-y-auto`

4. **使用開發者工具檢查**
   - 遇到版面問題時，先用瀏覽器開發者工具檢查 DOM 結構
   - 確認 flex 容器的 direction 是否正確

---

## 🚀 部署檢查清單

- [x] 修復 `index.html` 中的 flex 方向
- [ ] 重新啟動 WebUI 服務（如有必要）
- [ ] 清除瀏覽器快取（Ctrl + F5）
- [ ] 視覺確認版面已修復
- [ ] 執行功能測試清單

---

**修復完成時間：** 2026-03-31 16:12 GMT+8
**修復者：** AI Assistant
**影響範圍：** Chat Tab 的版面配置
