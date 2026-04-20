"""
LLM Mixin - 提供统一的 LLM 客户端访问和公共方法

遵循 DRY 原则，避免在多个类中重复定义 `_get_client`、`_get_model` 和 `_merge_page_artifacts` 方法。

使用方式：
```python
from nanobot.ingestion.utils.llm_mixin import LLMMixin

class FinancialAgent(LLMMixin):
    def __init__(self):
        super().__init__()
        # ... 其他初始化
    
    async def some_method(self):
        client = self._get_client()
        model = self._get_model()
        response = await client.chat(...)
        
        # 合并页面 artifacts
        merged_text = LLMMixin.merge_page_artifacts(page_artifacts)
```
"""

from typing import Dict, List, Any
from nanobot.core.llm_core import llm_core
from loguru import logger


class LLMMixin:
    """
    🌟 LLM Mixin - 提供统一的 LLM 客户端访问
    
    功能：
    - 延迟加载 LLM 客户端
    - 统一使用 llm_core
    - 避免重复定义
    
    使用方式：
    - 继承此 Mixin
    - 调用 `self._get_client()` 获取 llm_core
    - 调用 `self._get_model()` 获取默认模型名称
    """
    
    def __init__(self, *args, **kwargs):
        """初始化 Mixin"""
        super().__init__(*args, **kwargs)
        self._client = None
        self._model = None
    
    def _get_client(self):
        """
        获取 LLM 客户端（延迟加载）
        
        Returns:
            UnifiedLLMCore: llm_core 实例
        """
        if self._client is None:
            self._client = llm_core
            logger.debug(f"LLM client initialized: {self.__class__.__name__}")
        return self._client
    
    def _get_model(self) -> str:
        """
        获取 LLM 模型名称
        
        Returns:
            str: 默认模型名称（从 llm_core 获取）
        """
        if self._model is None:
            self._model = llm_core.default_model
        return self._model
    
    def _get_vision_model(self) -> str:
        """
        获取 Vision 模型名称
        
        Returns:
            str: Vision 模型名称（从 llm_core 获取）
        """
        return llm_core.vision_model
    
    @staticmethod
    def merge_page_artifacts(page_artifacts: List[Dict[str, Any]]) -> str:
        """
        🌟 合并页面 artifacts 为文本（静态方法，可直接调用）
        
        Args:
            page_artifacts: 页面级别的 artifacts
            
        Returns:
            str: 合并后的文本
            
        Example:
            merged_text = LLMMixin.merge_page_artifacts(page_artifacts)
        """
        merged = ""
        for artifact in page_artifacts:
            content = artifact.get("content", "") or artifact.get("markdown", "") or artifact.get("text", "")
            
            # 如果是表格，尝试提取 JSON 内容
            if artifact.get("type") == "table":
                table_json = artifact.get("content_json", {}) or artifact.get("content", {})
                if isinstance(table_json, dict):
                    import json
                    content = json.dumps(table_json, ensure_ascii=False)
            
            merged += content + "\n\n"
        
        return merged.strip()