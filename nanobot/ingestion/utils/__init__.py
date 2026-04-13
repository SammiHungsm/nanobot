"""
Utils Module - 共用工具

🎯 v2.0: 使用统一的 llm_core 封装
- 所有 LLM/Vision 调用统一在 nanobot.core.llm_core
- 不再需要单独的 llm_client.py
"""

# 🌟 从 llm_core 导入（替代 llm_client.py）
from nanobot.core.llm_core import (
    llm_core,
    chat,
    vision,
    get_api_config,
    detect_provider
)

# 🌟 提供兼容旧代码的函数别名
def get_llm_client():
    """兼容旧代码：返回 llm_core 实例"""
    return llm_core

def get_llm_model():
    """兼容旧代码：返回默认模型"""
    return llm_core.default_model

def get_vision_model():
    """兼容旧代码：返回视觉模型"""
    return llm_core.vision_model

def get_api_base():
    """兼容旧代码：返回 API Base"""
    return llm_core.config.get("api_base")

__all__ = [
    # 新的 llm_core
    "llm_core",
    "chat",
    "vision",
    "get_api_config",
    "detect_provider",
    # 兼容旧代码的别名
    "get_llm_client",
    "get_llm_model",
    "get_vision_model",
    "get_api_base"
]