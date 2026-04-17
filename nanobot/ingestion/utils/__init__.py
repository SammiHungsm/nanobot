"""
Utils Module - 共用工具

🎯 v2.0: 使用统一的 llm_core 封装
- 所有 LLM/Vision 调用统一在 nanobot.core.llm_core
- 直接导出 llm_core，不再需要兼容函数
"""

# 🌟 直接从 llm_core 导入（遵循 DRY 原则）
from nanobot.core.llm_core import (
    llm_core,
    chat,
    vision,
    get_api_config,
    detect_provider
)

__all__ = [
    "llm_core",
    "chat",
    "vision",
    "get_api_config",
    "detect_provider"
]