"""
LLM Core - 使用官方 Provider 系统的统一接口

🎯 不重新实现 Provider 路由，直接使用官方系统：
- config/loader.py → load_config()
- config/schema.py → Config.get_provider(), Config.get_api_key()
- providers/__init__.py → OpenAICompatProvider, AnthropicProvider
- providers/registry.py → PROVIDERS, ProviderSpec

统一接口：
- chat() - 文字对话
- vision() - 视觉解析（图片）
- detect_provider() - Provider 检测（包装官方函数）

Usage:
    from nanobot.core.llm_core import llm_core
    
    # 文字对话
    response = await llm_core.chat([{"role": "user", "content": "Hello"}])
    
    # 视觉解析
    result = await llm_core.vision(img_base64, "提取表格")
    
    # Provider 检测
    provider_name = detect_provider("gpt-4o")  # 返回 "openai"
"""

import os
import base64
from typing import List, Dict, Any, Optional
from loguru import logger

# 🌟 使用官方的 Config 系统
try:
    from nanobot.config.loader import load_config, resolve_config_env_vars
    from nanobot.config.schema import Config, ProviderConfig
    NANOBOT_CONFIG_AVAILABLE = True
except ImportError:
    NANOBOT_CONFIG_AVAILABLE = False
    logger.warning("⚠️ nanobot config system not available")

# 🌟 使用官方的 Provider 系统
try:
    from nanobot.providers import OpenAICompatProvider, AnthropicProvider
    from nanobot.providers.base import LLMResponse, ToolCallRequest
    from nanobot.providers.registry import PROVIDERS, find_by_name
    NANOBOT_PROVIDERS_AVAILABLE = True
except ImportError:
    NANOBOT_PROVIDERS_AVAILABLE = False
    logger.warning("⚠️ nanobot providers not available")


def detect_provider(model_name: str) -> Optional[str]:
    """
    🎯 Provider 检测函数（包装官方逻辑）
    
    Args:
        model_name: 模型名称（如 "gpt-4o", "claude-3", "ollama/llava"）
        
    Returns:
        str: Provider 名称（如 "openai", "anthropic", "ollama"）
        
    Example:
        provider = detect_provider("gpt-4o")  # 返回 "openai"
        provider = detect_provider("claude-3")  # 返回 "anthropic"
        provider = detect_provider("ollama/llava")  # 返回 "ollama"
    """
    if not NANOBOT_PROVIDERS_AVAILABLE:
        return "openai"  # Fallback
    
    model_lower = model_name.lower()
    
    # 🌟 使用官方 PROVIDERS 的 keywords 匹配
    for spec in PROVIDERS:
        if any(kw in model_lower for kw in spec.keywords):
            return spec.name
    
    # 特殊处理：ollama/ 前缀
    if model_name.startswith("ollama/"):
        return "ollama"
    
    # 默认：OpenAI
    return "openai"


class UnifiedLLMCore:
    """
    统一的 LLM/Vision 客户端
    
    🌟 使用官方的 Provider 系统，不重新实现路由逻辑
    
    官方架构：
    - Config.get_provider(model) → 返回匹配的 ProviderConfig
    - Config.get_api_key(model) → 返回 API Key
    - Config.get_api_base(model) → 返回 API Base URL
    - OpenAICompatProvider / AnthropicProvider → 具体实现
    
    Example:
        llm = UnifiedLLMCore()
        response = await llm.chat([{"role": "user", "content": "Hello"}])
    """
    
    def __init__(self):
        """
        初始化
        
        🌟 使用官方的 Config 系统
        """
        # 加载官方配置
        if NANOBOT_CONFIG_AVAILABLE:
            config_path_env = os.getenv("NANOBOT_CONFIG")
            from pathlib import Path
            config_path = Path(config_path_env) if config_path_env else None
            
            self.config: Config = resolve_config_env_vars(load_config(config_path))
            self.default_model = self.config.agents.defaults.model
            # 🌟 Vision 模型跟随 config.json（优先级：env var > config.json > 默认值）
            self.vision_model = os.getenv("VISION_MODEL") or getattr(self.config.agents.defaults, 'vision_model', 'gpt-4o')
            
            logger.info(f"✅ UnifiedLLMCore initialized using official config (model={self.default_model}, vision={self.vision_model})")
        else:
            self.config = None
            self.default_model = os.getenv("DEFAULT_LLM_MODEL", "gpt-4o-mini")
            self.vision_model = os.getenv("VISION_MODEL", "gpt-4o")
            logger.warning("⚠️ Using fallback config (official config unavailable)")
        
        # Provider 实例（延迟初始化）
        self._provider_cache: Dict[str, Any] = {}
    
    def _get_provider(self, model: str = None) -> Optional[Any]:
        """
        🌟 使用官方的 Provider 系统
        
        Args:
            model: 模型名称
            
        Returns:
            Provider 实例（OpenAICompatProvider 或 AnthropicProvider）
        """
        if not NANOBOT_PROVIDERS_AVAILABLE:
            logger.error("❌ nanobot providers not available")
            return None
        
        target_model = model or self.default_model
        
        # 🌟 使用官方的 Provider 匹配逻辑
        provider_name = self.config.get_provider_name(target_model) if self.config else None
        
        if provider_name:
            # 检查缓存
            if provider_name in self._provider_cache:
                return self._provider_cache[provider_name]
            
            # 🌟 使用官方的 Provider Registry
            spec = find_by_name(provider_name)
            if spec:
                # 获取配置
                provider_config = self.config.get_provider(target_model) if self.config else None
                
                # 🌟 正确的 Provider 初始化方式（使用关键字参数）
                if spec.backend == "anthropic":
                    provider = AnthropicProvider(
                        api_key=provider_config.api_key if provider_config else None,
                        api_base=provider_config.api_base if provider_config else None,
                        spec=spec,
                        extra_headers=provider_config.extra_headers if provider_config else None
                    )
                else:
                    # OpenAI-compatible（包括 OpenAI, DashScope, Ollama 等）
                    provider = OpenAICompatProvider(
                        api_key=provider_config.api_key if provider_config else None,
                        api_base=provider_config.api_base if provider_config else None,
                        spec=spec,
                        extra_headers=provider_config.extra_headers if provider_config else None
                    )
                
                self._provider_cache[provider_name] = provider
                logger.debug(f"🤖 Created provider: {provider_name} for model {target_model}")
                return provider
        
        # Fallback: 使用第一个可用的 Provider
        logger.warning(f"⚠️ No provider found for model {target_model}, using first available")
        
        # 🌟 遍历 PROVIDERS registry
        for spec in PROVIDERS:
            if spec.is_oauth:  # OAuth provider 需要 explicit model selection
                continue
            
            provider_config = getattr(self.config.providers, spec.name, None) if self.config else None
            
            if provider_config and (provider_config.api_key or spec.is_local):
                if spec.backend == "anthropic":
                    return AnthropicProvider(
                        api_key=provider_config.api_key,
                        api_base=provider_config.api_base,
                        spec=spec,
                        extra_headers=provider_config.extra_headers
                    )
                else:
                    return OpenAICompatProvider(
                        api_key=provider_config.api_key,
                        api_base=provider_config.api_base,
                        spec=spec,
                        extra_headers=provider_config.extra_headers
                    )
        
        logger.error("❌ No available provider found")
        return None
    
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        tools: List[Dict[str, Any]] = None,  # 🌟 新增：Function Calling 支持
        tool_choice: str = None,  # 🌟 新增：Tool 选择策略
        return_response: bool = False,  # 🌟 新增：返回完整 LLMResponse
        **kwargs
    ) -> str | LLMResponse:
        """
        🎯 统一的文字对话接口
        
        Args:
            messages: OpenAI 格式的 messages 列表
            model: 模型名称（默认使用 default_model）
            temperature: 温度参数
            max_tokens: 最大输出长度
            tools: Function Calling 工具列表（OpenAI 格式）
            tool_choice: Tool 选择策略 ("auto", "required", "none")
            return_response: 如果 True，返回完整 LLMResponse（包含 tool_calls）
            
        Returns:
            str | LLMResponse: LLM 的回复文本，或完整的 LLMResponse
        """
        target_model = model or self.default_model
        provider = self._get_provider(target_model)
        
        if not provider:
            logger.error("❌ Provider not available")
            raise RuntimeError("Provider not available. Check config and API keys.")
        
        # 🌟 使用配置中的默认值
        if temperature is None:
            temperature = self.config.agents.defaults.temperature if self.config else 0.7
        
        if max_tokens is None:
            max_tokens = self.config.agents.defaults.max_tokens if self.config else 2000
        
        logger.debug(f"🤖 Calling LLM: {target_model} (tools={len(tools) if tools else 0})")
        
        try:
            # 🌟 调用官方的 Provider（支持 tools）
            response: LLMResponse = await provider.chat_with_retry(
                model=target_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                **kwargs
            )
            
            if return_response:
                # 🌟 返回完整 LLMResponse（包含 tool_calls）
                return response
            
            content = response.content or ""
            logger.debug(f"✅ LLM response: {len(content)} chars, tool_calls={len(response.tool_calls)}")
            return content
            
        except Exception as e:
            logger.error(f"❌ LLM call failed: {e}")
            raise
    
    async def vision(
        self,
        image_base64: str,
        prompt: str,
        model: str = None,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> str:
        """
        🎯 统一的视觉解析接口
        
        Args:
            image_base64: 图片的 Base64 编码（不带 data:image 前缀）
            prompt: 给 Vision 模型的提示词
            model: Vision 模型名称（默认使用 vision_model）
            temperature: 温度参数
            max_tokens: 最大输出长度
            
        Returns:
            str: Vision 模型的分析结果
        """
        target_model = model or self.vision_model
        provider = self._get_provider(target_model)
        
        if not provider:
            logger.error("❌ Provider not available")
            raise RuntimeError("Provider not available. Check config and API keys.")
        
        logger.debug(f"👁️ Calling Vision: {target_model}")
        
        # 🌟 构建 Vision 请求（OpenAI 格式）
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ]
        
        try:
            # 🌟 调用官方的 Provider（Vision 使用 chat 方法）
            response: LLMResponse = await provider.chat(
                model=target_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            content = response.content or ""
            logger.debug(f"✅ Vision response: {len(content)} chars")
            return content
            
        except Exception as e:
            logger.error(f"❌ Vision call failed: {e}")
            raise
    
    async def batch_chat(
        self,
        prompts: List[str],
        model: str = None,
        **kwargs
    ) -> List[str]:
        """
        🎯 批量文字对话（并发调用）
        
        Args:
            prompts: 多个提示词列表
            model: 模型名称
            
        Returns:
            List[str]: 多个回复文本
        """
        import asyncio
        
        tasks = [
            self.chat([{"role": "user", "content": p}], model=model, **kwargs)
            for p in prompts
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        output = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"⚠️ Batch item {i} failed: {result}")
                output.append("")
            else:
                output.append(result)
        
        return output
    
    async def batch_vision(
        self,
        images: List[str],
        prompt: str,
        model: str = None
    ) -> List[str]:
        """
        🎯 批量视觉解析（并发调用）
        
        Args:
            images: 多个图片的 Base64 编码列表
            prompt: 统一的提示词
            model: Vision 模型
            
        Returns:
            List[str]: 多个分析结果
        """
        import asyncio
        
        tasks = [
            self.vision(img, prompt, model=model)
            for img in images
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        output = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"⚠️ Batch vision item {i} failed: {result}")
                output.append("")
            else:
                output.append(result)
        
        return output


# ===========================================
# 全域單例
# ===========================================

llm_core = UnifiedLLMCore()


# ===========================================
# 便捷函数
# ===========================================

async def chat(prompt: str, model: str = None, **kwargs) -> str:
    """
    便捷函数：快速文字对话
    
    Args:
        prompt: 提示词（字符串）
        model: 模型名称
        
    Returns:
        str: LLM 回复
    """
    return await llm_core.chat([{"role": "user", "content": prompt}], model=model, **kwargs)


async def vision(image_path_or_base64: str, prompt: str, model: str = None) -> str:
    """
    便捷函数：快速视觉解析
    
    Args:
        image_path_or_base64: 图片路径或 Base64 编码
        prompt: 提示词
        model: Vision 模型
        
    Returns:
        str: Vision 分析结果
    """
    # 🌟 自动处理图片输入
    if os.path.exists(image_path_or_base64):
        with open(image_path_or_base64, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()
    else:
        img_base64 = image_path_or_base64
    
    return await llm_core.vision(img_base64, prompt, model=model)


# ===========================================
# 兼容旧代码的函数（不再需要，但保留别名）
# ===========================================

def get_llm_client() -> UnifiedLLMCore:
    """兼容旧代码：返回 llm_core 实例"""
    return llm_core

def get_llm_model() -> str:
    """兼容旧代码：返回默认模型"""
    return llm_core.default_model

def get_vision_model() -> str:
    """兼容旧代码：返回视觉模型"""
    return llm_core.vision_model

def get_api_base() -> str:
    """兼容旧代码：返回 API Base"""
    if llm_core.config:
        return llm_core.config.get_api_base() or ""
    return ""

def get_api_config() -> Dict[str, Any]:
    """兼容旧代码：返回 API 配置"""
    return {
        "api_key": llm_core.config.get_api_key() if llm_core.config else None,
        "api_base": get_api_base(),
        "default_model": llm_core.default_model,
        "vision_model": llm_core.vision_model
    }


# ===========================================
# 测试
# ===========================================

if __name__ == "__main__":
    import asyncio
    
    print("🧪 测试 UnifiedLLMCore (使用官方 Provider 系统)")
    
    # 测试配置
    print("\n1. 测试配置:")
    print(f"   Config available: {NANOBOT_CONFIG_AVAILABLE}")
    print(f"   Providers available: {NANOBOT_PROVIDERS_AVAILABLE}")
    print(f"   Default model: {llm_core.default_model}")
    print(f"   Vision model: {llm_core.vision_model}")
    
    # 测试 Provider 匹配
    print("\n2. 测试 Provider 匹配:")
    test_models = ["gpt-4o", "claude-3", "qwen-plus", "ollama/llava"]
    for model in test_models:
        provider = llm_core._get_provider(model)
        print(f"   {model} → {provider.__class__.__name__ if provider else 'None'}")
    
    # 测试 chat
    print("\n3. 测试 chat:")
    try:
        response = asyncio.run(chat("Hello, 你是谁？"))
        print(f"   回复: {response[:100]}...")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    print("\n✅ 测试完成")