# OpenDataLoader 修復記錄

## 🔧 最新修復 (2026-04-12 08:30)

### 問題：`pages="all"` 參數錯誤

**錯誤信息**:
```
Invalid page range format: 'all'. Expected format: 1,3,5-7
```

**原因**: 
OpenDataLoader CLI 的 `--pages` 參數不接受 `"all"` 字串。

**CLI 文檔**:
```
--pages <arg>   Pages to extract (e.g., "1,3,5-7"). Default: all pages
```

**解決方案**: 
**不要傳遞 `pages` 參數**，默認就是所有頁面。

---

## ✅ 正確的 API 調用

```python
from opendataloader_pdf import convert

# ✅ 正確的寫法
convert(
    input_path=pdf_path,          # str 或 list
    output_dir=temp_dir,          # 目錄路徑
    format="json",                # 輸出格式
    # pages=None,                 # ⚠️ 不傳 pages，默處理所有頁面
    image_output="embedded",      # Base64 data URIs
    image_format="png"            # 圖片格式
)

# ❌ 錯誤的寫法
convert(
    ...
    pages="all",                  # ❌ CLI 不接受 "all"
    ...
)

# ✅ 如果要指定特定頁面
convert(
    ...
    pages="1,3,5-7",              # ✅ 正確格式
    ...
)
```

---

## 🚀 重新啟動服務

修復完成後，請重新啟動 Docker 服務：

```bash
# 在 sfc_poc 目錄下
docker-compose restart nanobot-webui

# 或重新啟動所有服務
docker-compose down && docker-compose up -d
```

---

## 📚 參考

- [OpenDataLoader GitHub](https://github.com/opendataloader-project/opendataloader-pdf)
- CLI `--pages` 參數：`Pages to extract (e.g., "1,3,5-7"). Default: all pages`