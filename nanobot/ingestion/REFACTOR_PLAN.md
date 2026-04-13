# 架构整合计划 - Pipeline 继承方案

## 当前状态

### 问题
旧的 `pipeline.py` (`DocumentPipeline`, 900+ 行) 没有继承 `BaseIngestionPipeline`，导致系统有"两套"Pipeline并存：
- `BaseIngestionPipeline` (250 行) - 新的基类
- `DocumentPipeline` (900 行) - 旧的巨无霸 Pipeline

### 影响
- **代码冗余**：两套 Pipeline 有 80% 的逻辑重复
- **维护困难**：修改一处，另一处不会同步更新
- **难以扩展**：新增 Pipeline 类型需要大量复制粘贴

## 整合方案

### 方案 A：渐进式重构（推荐）

**步骤 1：标记旧 Pipeline 为"Legacy"**
```python
# pipeline.py
class LegacyDocumentPipeline:  # 改名，标记为旧版
    """旧版 Pipeline（已废弃，建议使用 BaseIngestionPipeline）"""
    ...
```

**步骤 2：新版 Pipeline 继承基类**
```python
# 新建 document_pipeline.py
from nanobot.ingestion.base_pipeline import BaseIngestionPipeline

class DocumentPipeline(BaseIngestionPipeline):
    """新版 DocumentPipeline（继承基类）"""
    
    async def extract_information(self, artifacts, **kwargs):
        """覆写提取逻辑：使用硬编码 + Agent 混合"""
        # 将旧的 smart_extract 逻辑搬到这里
        return await self._smart_extract(artifacts, **kwargs)
    
    async def _smart_extract(self, artifacts, **kwargs):
        """从旧的 pipeline.py 迁移过来的提取逻辑"""
        # ... (逐步迁移)
```

**步骤 3：WebUI 切换到新版 Pipeline**
```python
# document_service.py
from nanobot.ingestion.document_pipeline import DocumentPipeline  # 新版

pipeline = DocumentPipeline(db_url=self._db_url, data_dir=self._data_dir)
```

**优点**：
- 渐进式迁移，风险可控
- 可以逐步拆解旧的 900 行代码
- WebUI 可以平滑切换

**缺点**：
- 需要较长时间（建议分多次 PR）

---

### 方案 B：一次性重构（激进）

**步骤 1：将 DocumentPipeline 改为继承 BaseIngestionPipeline**
```python
# pipeline.py
from nanobot.ingestion.base_pipeline import BaseIngestionPipeline

class DocumentPipeline(BaseIngestionPipeline):
    """文档 Pipeline（继承基类）"""
    
    def __init__(self, db_url, data_dir, ...):
        super().__init__(db_url, data_dir, ...)
        # 保留原有的初始化逻辑
    
    async def extract_information(self, artifacts, **kwargs):
        """覆写提取逻辑"""
        # 将 smart_extract 的核心逻辑搬到这里
        # 删除其他重复的方法（parse_document, save_to_db 等）
        ...
```

**步骤 2：删除重复的方法**
- 删除 `parse_document()`（基类已提供）
- 删除 `save_to_db()` 相关方法（基类已提供）
- 只保留 `extract_information()` 的实现

**优点**：
- 一次性解决架构问题
- 减少 50% 的代码量

**缺点**：
- 需要大量修改，可能影响现有功能
- 测试工作量较大

---

## 建议

**第一阶段（现在）**：
- 修复致命 Bug（已完成）
- 创建新的 `AgenticPipeline`（已完成）
- 创建新的 `batch_processor.py`（已完成）

**第二阶段（下一步）**：
- 将 `DocumentPipeline` 的核心方法（`smart_extract`, `process_pdf_full`）拆分成独立的函数
- 这些函数可以被 `BaseIngestionPipeline` 的子类调用

**第三阶段（长期）**：
- 逐步迁移 `DocumentPipeline` 的逻辑到 `BaseIngestionPipeline` 的子类
- 最终删除旧的 `pipeline.py`（或标记为 Legacy）

---

## 当前状态总结

| 组件 | 状态 | 下一步 |
|------|------|--------|
| `base_pipeline.py` | ✅ 已修复 import 位置 | 稳定 |
| `agentic_pipeline.py` | ✅ 已创建 | 稳定 |
| `batch_processor.py` | ✅ 已创建 | 稳定 |
| `llm_core.py` | ✅ 已添加 Provider 路由 | 稳定 |
| `pdf_core.py` | ✅ 已创建 | 稳定 |
| `pipeline.py` (旧) | ⚠️ 未整合 | **建议使用方案 A（渐进式重构）** |

---

## 用户决定

请选择：
- **方案 A**：渐进式重构（分多次迁移，风险低）
- **方案 B**：一次性重构（大量修改，风险高）
- **暂不处理**：先让新旧 Pipeline 并存，后续再整合

建议：**选择方案 A**，先让系统稳定运行，后续逐步迁移。