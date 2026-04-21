# 系統級 Auto Type Casting

## 📋 概述

在 Tool 執行引擎中實現自動類型轉換，根據 Tool 的 JSON Schema 自動將 LLM 傳遞的參數轉換為正確的資料型態。

## 🎯 解決的問題

LLM 經常會傳遞錯誤的資料型態：
- 傳遞字串 `"1"` 而不是整數 `1`
- 傳遞字串 `"123.45"` 而不是浮點數 `123.45`
- 傳遞字串 `"true"` 而不是布林值 `True`

這會導致 `asyncpg` 或其他嚴格類型檢查的庫報錯：
```
str object cannot be interpreted as an integer
```

## 🛠️ 實現位置

### 1. Gateway Agent Runner

**文件**: `nanobot/agent/runner.py`

**方法**: `_run_tool()`

**位置**: 在 `tool.execute(**params)` 之前

### 2. Ingestion Agentic Executor

**文件**: `nanobot/ingestion/agentic_executor.py`

**方法**: `_execute_tool()`

**位置**: 在 `execute_func(**tool_args)` 之前

## 🔧 核心邏輯

```python
# 🌟 系統級優化：Auto Type Casting (根據 Tool 的 Schema 自動轉型)
if hasattr(tool, 'parameters'):
    properties = tool.parameters.get("properties", {})
    
    for key, val in params.items():
        if key in properties and val is not None:
            # 獲取 Schema 中定義的預期類型
            expected_type = properties[key].get("type")
            
            try:
                if expected_type == "integer":
                    # 如果預期是整數，但 LLM 傳了字串 "1" 或浮點數 1.0
                    if isinstance(val, str):
                        params[key] = int(float(val))
                    elif isinstance(val, float):
                        params[key] = int(val)
                elif expected_type == "number":
                    # 如果預期是浮點數，但 LLM 傳了字串 "123.45"
                    if isinstance(val, str):
                        params[key] = float(val)
                elif expected_type == "boolean":
                    # 處理 "true", "False", "1" 等各種布林字串
                    if isinstance(val, str):
                        params[key] = val.lower() in ("true", "1", "yes", "t")
                    elif isinstance(val, (int, float)):
                        params[key] = bool(val)
                elif expected_type == "string":
                    # 強制轉字串
                    params[key] = str(val)
            except (ValueError, TypeError) as e:
                # 如果 LLM 傳了完全無法轉換的東西 (例如 "abc" 轉 int)，
                # 這裡放行保留原值，讓 Tool 執行時自己報錯
                logger.warning(f"⚠️ 自動轉型失敗: {key}={val} (預期: {expected_type})")
                pass
```

## ✅ 優點

1. **一勞永逸 (DRY Principle)**
   - 不需要在每個 Tool 中手動寫 `int()` 或 `float()` 防呆
   - 只需在 Tool 的 `parameters` 中正確定義 `"type": "integer"`

2. **自動映射 Schema**
   - 只要 Tool 定義了正確的 JSON Schema，執行引擎會自動把關

3. **完美處理 LLM 的幻覺**
   - LLM 分不清楚數字 `1` 和字串 `"1"`，這段程式碼自動吸收這個問題
   - 徹底消滅 `str object cannot be interpreted as an integer` 錯誤

## 📝 使用範例

### Tool 定義

```python
class InsertRevenueBreakdownTool(Tool):
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": "integer",  # 🌟 定義為整數
                    "description": "公司 ID"
                },
                "year": {
                    "type": "integer",  # 🌟 定義為整數
                    "description": "年份"
                },
                "amount": {
                    "type": "number",  # 🌟 定義為浮點數
                    "description": "金額"
                }
            },
            "required": ["company_id", "year"]
        }
```

### LLM 調用

LLM 可能會這樣調用：

```json
{
  "company_id": "3",      // ❌ 字串，應該是整數
  "year": "2023",         // ❌ 字串，應該是整數
  "amount": "123.45"      // ❌ 字串，應該是浮點數
}
```

### 自動轉換後

執行引擎會自動轉換為：

```json
{
  "company_id": 3,        // ✅ 整數
  "year": 2023,           // ✅ 整數
  "amount": 123.45        // ✅ 浮點數
}
```

## 🚨 注意事項

1. **轉換失敗處理**
   - 如果無法轉換（例如 `"abc"` 轉 `int`），會保留原值
   - 讓 Tool 執行時自己報錯，提供更好的錯誤訊息

2. **Null 值處理**
   - `None` 值會被跳過，不做轉換

3. **嵌套物件**
   - 目前只處理頂層參數
   - 嵌套在物件內的值需要 Tool 自己處理

## 📊 效果

| 指標 | 改進前 | 改進後 |
|------|--------|--------|
| Tool 防呆代碼 | 每個 Tool 都要寫 | 零代碼 |
| 類型錯誤率 | 高 | 接近零 |
| 維護成本 | 高 | 低 |
| 開發效率 | 低 | 高 |

## 🎯 總結

這是一個**系統級架構優化**，徹底解決了 LLM 傳遞錯誤資料型態的問題。開發者只需在 Tool 的 `parameters` 中正確定義類型，執行引擎會自動處理剩下的工作。
