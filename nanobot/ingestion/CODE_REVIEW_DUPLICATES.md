# Ingestion Code Review - 重复代码 & 可重用函数分析

**Review Date:** 2026-04-24  
**Reviewer:** Agent  
**Version:** v4.8

---

## 📋 目录

1. [发现的重复代码](#1-发现的重复代码)
2. [可重用的公共函数](#2-可重用的公共函数)
3. [建议的重构计划](#3-建议的重构计划)
4. [其他问题](#4-其他问题)

---

## 1. 发现的重复代码

### 🔴 重复 #1: `_parse_json_response` 方法

**位置:**
- `stages/stage4_agentic_extractor.py` (line ~400)
- `stages/stage4_fallback_extractor.py` (line ~180)

**问题:** 两个文件有完全相同的 JSON 解析逻辑

```python
# Stage4FallbackExtractor 中的实现
@staticmethod
def _parse_json_response(response: str) -> List[Dict]:
    try:
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response
        
        data = json.loads(json_str)
        
        if isinstance(data, dict):
            for key in ['segments', 'shareholders', 'data', 'result']:
                if key in data:
                    return data[key]
            return [data]
        
        if isinstance(data, list):
            return data
        
        return []
        
    except json.JSONDecodeError as e:
        logger.warning(f"   ⚠️ JSON 解析失败: {e}")
        return []
```

**建议:** 提取到 `utils/json_utils.py`

```python
# utils/json_utils.py
import json
import re
from typing import List, Dict, Any
from loguru import logger

def parse_llm_json_response(response: str, wrap_keys: List[str] = None) -> List[Dict]:
    """
    解析 LLM 返回的 JSON 响应
    支持从代码块中提取 JSON，自动解包常见包装结构
    
    Args:
        response: LLM 原始响应
        wrap_keys: 常见的包装 key 列表，如 ['segments', 'shareholders', 'data']
    
    Returns:
        List[Dict]: 解析后的数据列表
    """
    wrap_keys = wrap_keys or ['segments', 'shareholders', 'data', 'result']
    
    try:
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        json_str = json_match.group(1) if json_match else response
        
        data = json.loads(json_str)
        
        if isinstance(data, dict):
            for key in wrap_keys:
                if key in data:
                    return data[key]
            return [data]
        
        if isinstance(data, list):
            return data
        
        return []
        
    except json.JSONDecodeError as e:
        logger.warning(f"   ⚠️ JSON 解析失败: {e}")
        return []
```

---

### 🔴 重复 #2: `_get_precise_context` / `RAG-Anything` 上下文提取

**位置:**
- `stages/stage2_enrichment.py` (line ~130) - `_get_precise_context`
- `stages/stage3_5_context_builder.py` - 也有类似逻辑

**问题:** 精准上下文提取逻辑分散在多处

```python
# Stage2Enrichment 中的实现
@staticmethod
def _get_precise_context(artifacts: List[Dict[str, Any]], target_idx: int) -> Dict[str, str]:
    context = {
        "closest_heading": "無明確標題",
        "previous_text": "",
        "caption": "",
        "next_text": ""
    }
    
    # 往前找 (尋找標題和前文)
    for i in range(target_idx - 1, -1, -1):
        artifact = artifacts[i]
        if artifact is None or artifact.get("type") != "text":
            continue
        # ... 逻辑 ...
    
    # 往後找 (尋找圖表後的解釋分析)
    for i in range(target_idx + 1, min(target_idx + 5, len(artifacts))):
        # ... 逻辑 ...
    
    return context
```

**建议:** 提取到 `utils/rag_context.py`

```python
# utils/rag_context.py
from typing import Dict, List, Any

def extract_precise_context(
    artifacts: List[Dict[str, Any]], 
    target_idx: int,
    max_look_back: int = 10,
    max_look_forward: int = 5
) -> Dict[str, str]:
    """
    RAG-Anything 风格的精准上下文提取
    提取：最近的标题、前文、图说、后文
    
    Args:
        artifacts: 所有 artifact 列表
        target_idx: 目标 artifact 的索引
        max_look_back: 向前查找的最大 artifact 数
        max_look_forward: 向后查找的最大 artifact 数
    
    Returns:
        Dict: {
            "closest_heading": str,
            "previous_text": str,
            "caption": str,
            "next_text": str
        }
    """
    # ... 实现 ...
```

---

### 🟡 重复 #3: `insert_processing_history` 调用模式

**位置:**
- `pipeline.py` 中多处调用 `await self.db.insert_processing_history(...)`

**问题:** 每个 Stage 后都手动调用，代码重复

```python
# pipeline.py 中的重复代码
# Stage 0
await self.db.insert_processing_history(
    document_id=document_id,
    stage="stage0",
    status="success",
    message="Vision 提取封面完成",
    artifacts_count=1
)

# Stage 0.5
await self.db.insert_processing_history(
    document_id=document_id,
    stage="stage0_5",
    status="success",
    message="文档和公司注册完成",
    artifacts_count=2
)

# Stage 1
await self.db.insert_processing_history(
    document_id=document_id,
    stage="stage1",
    status="success",
    message=f"LlamaParse 解析完成，job_id={parse_result.job_id}",
    artifacts_count=len(artifacts)
)
# ... 更多重复 ...
```

**建议:** 创建 Pipeline 辅助方法

```python
# 在 pipeline.py 中添加
async def _record_stage(self, document_id: int, stage: str, message: str, artifacts_count: int = 0, status: str = "success"):
    """记录 Stage 执行历史"""
    if self.db and document_id:
        await self.db.insert_processing_history(
            document_id=document_id,
            stage=stage,
            status=status,
            message=message,
            artifacts_count=artifacts_count
        )

# 使用方式
await self._record_stage(document_id, "stage0", "Vision 提取封面完成", 1)
await self._record_stage(document_id, "stage0_5", "文档和公司注册完成", 2)
```

---

### 🟡 重复 #4: `keyword` 扫描逻辑

**位置:**
- `stages/stage3_router.py` - `_check_keywords` 和 `_flatten_keywords`
- `extractors/page_classifier.py` - 可能有类似逻辑

**问题:** 关键字匹配逻辑可以更模块化

**建议:** 提取到 `utils/keyword_matcher.py`

---

### 🟡 重复 #5: `build_content_text` 内容拼接

**位置:**
- `stage4_agentic_extractor.py` 中的 `run_agentic_write` 方法 (约 line 250-290)
- `stage4_fallback_extractor.py` 中的内容准备逻辑

**问题:** 构建用户消息时，内容拼接逻辑类似

```python
# Stage4AgenticExtractor 中的代码
content_parts = []
for page_num in sorted_pages:
    if page_num <= len(artifacts):
        artifact = artifacts[page_num - 1]
        content = artifact.get("content", "") or artifact.get("markdown", "") or ""
        if content:
            content_parts.append(f"=== 第 {page_num} 页 ===\n{content}")

content_text = "\n\n".join(content_parts)
```

**建议:** 提取到 `utils/content_builder.py`

```python
# utils/content_builder.py
def build_page_content_text(
    artifacts: List[Dict[str, Any]], 
    page_nums: List[int],
    prefix: str = "=== 第 {page} 页 ==="
) -> str:
    """
    从指定页面构建内容文本
    
    Args:
        artifacts: 所有 artifact 列表
        page_nums: 要包含的页面编号列表
        prefix: 每个页面的前缀格式
    
    Returns:
        str: 拼接后的内容文本
    """
    content_parts = []
    for page_num in sorted(page_nums):
        if page_num <= len(artifacts):
            artifact = artifacts[page_num - 1]
            content = artifact.get("content", "") or artifact.get("markdown", "") or ""
            if content:
                content_parts.append(f"{prefix.format(page=page_num)}\n{content}")
    
    return "\n\n".join(content_parts)
```

---

## 2. 可重用的公共函数

### ✅ 已存在的公共模块

| 模块 | 位置 | 用途 | 状态 |
|------|------|------|------|
| `LLMMixin` | `utils/llm_mixin.py` | 统一 LLM 客户端访问 | ✅ 存在但未被充分使用 |
| `PDFParser` | `nanobot/core/pdf_core.py` | 统一 PDF 解析 | ✅ 遵循 |
| `llm_core` | `nanobot/core/llm_core.py` | 统一 LLM 调用 | ✅ 遵循 |

### 🆕 建议新增的公共模块

| 模块 | 位置 | 用途 |
|------|------|------|
| `json_utils.py` | `utils/json_utils.py` | JSON 解析公共函数 |
| `rag_context.py` | `utils/rag_context.py` | RAG 上下文提取 |
| `content_builder.py` | `utils/content_builder.py` | 内容拼接构建 |
| `keyword_matcher.py` | `utils/keyword_matcher.py` | 关键字匹配 |
| `artifact_helpers.py` | `utils/artifact_helpers.py` | Artifact 类型判断和处理 |

---

## 3. 建议的重构计划

### Phase 1: 紧急修复

1. **修复 Stage6Validator 中的日志信息错误**
   - 文件名: `stages/stage6_validator.py`
   - 问题: 注释说是 `Stage 6`，但日志输出 `Stage 7`
   
   ```python
   # 错误
   logger.info(f"🔍 Stage 7: 验证 Revenue Breakdown...")
   
   # 应该
   logger.info(f"🔍 Stage 6: 验证 Revenue Breakdown...")
   ```

2. **统一 `_parse_json_response`**
   - 创建 `utils/json_utils.py`
   - 两个文件都改为调用公共函数

### Phase 2: 中期重构

3. **统一 RAG-Anything 上下文提取**
   - 创建 `utils/rag_context.py`
   - `Stage2Enrichment._get_precise_context` → 使用公共函数
   - `Stage3_5_ContextBuilder` → 使用公共函数

4. **Pipeline 辅助方法**
   - 在 `pipeline.py` 添加 `_record_stage()` 辅助方法
   - 减少重复的 `insert_processing_history` 调用

### Phase 3: 长期优化

5. **内容构建器**
   - 创建 `utils/content_builder.py`
   - 统一内容拼接逻辑

6. **Artifact 处理工具**
   - 创建 `utils/artifact_helpers.py`
   - 统一 artifact 类型判断、过滤等操作

---

## 4. 其他问题

### ⚠️ 问题 #1: Stage6Validator 版本注释不一致

**文件:** `stages/stage6_validator.py`

```python
"""
Stage 6: Validator & Normalizer (v4.0)
...
🌟 v4.0: 简化后的 Stage 6（原 Stage 7）
```

日志却输出 `Stage 7`，这是遗留问题。

### ⚠️ 问题 #2: 注释中的 TODO 未完成

**文件:** `stages/stage4_agentic_extractor.py`

```python
# ❌ 移除 InsertArtifactRelationTool - Agent 无法看到 UUID，改用 entity_resolver.py 的 Regex 处理
```

但 `InsertArtifactRelationTool` 仍在 `_build_tools_registry` 的注释中列出，可能需要清理。

### ⚠️ 问题 #3: `run_agentic_write` 方法过长

**文件:** `stages/stage4_agentic_extractor.py`

`run_agentic_write` 方法超过 400 行，包含：
- System prompt 构建
- 用户消息构建（两种分支）
- Executor 调用

**建议:** 拆分为多个辅助方法：
- `_build_system_prompt()`
- `_build_user_message_with_context()`
- `_build_user_message_fallback()`

---

## 📊 统计摘要

| 类别 | 数量 |
|------|------|
| 重复代码块 | 5 |
| 可重用函数识别 | 4 |
| 需要修复的问题 | 3 |
| 建议新增的公共模块 | 5 |

---

## ✅ 优先处理顺序

1. **高优先级:** 
   - `json_utils.py` 创建（消除重复）
   - `Stage6Validator` 日志修复

2. **中优先级:**
   - `rag_context.py` 创建（统一上下文提取）
   - Pipeline `_record_stage` 辅助方法

3. **低优先级:**
   - 内容构建器
   - `run_agentic_write` 方法拆分
